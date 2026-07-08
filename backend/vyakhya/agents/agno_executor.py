"""The real Agno agent pipeline.

Implements the same ``PipelineExecutor`` async-iterator contract as the
simulated executor (status/log/flag/scenes/progress/done events), but drives a
real Agno agent — wired with the vendored HyperFrames **LocalSkills** — to turn
the paper into Scene-JSON. Selected when ``USE_AGNO`` is on, the ``agents`` extra
is installed, and an LLM connection is configured; otherwise the app falls back
to the simulated executor.

The design-time visual-designer agent loads the HyperFrames skills so it authors
scenes against the same contract the render service enforces.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from vyakhya.agents.model_factory import build_llm_model
from vyakhya.agents.pipeline import AGENT_SEQUENCE, _event
from vyakhya.agents.skills import get_hyperframes_skills
from vyakhya.core.database import get_sessionmaker
from vyakhya.core.logging import get_logger
from vyakhya.db.models.config import AgentModelAssignment, ProviderConnection
from vyakhya.db.models.project import Project
from vyakhya.enums import (
    AgentId,
    AgentStatus,
    AudienceLevel,
    CaptionStyle,
    PipelineEventType,
    ProviderKind,
    SceneTransition,
    VisualType,
)
from vyakhya.services.crypto import get_encryptor
from vyakhya.utils import new_id

log = get_logger(__name__)


# ── Generation schema (no ids/index — the persistence layer assigns those) ────
# `alias` (not serialization_alias) so the model output (camelCase) both feeds
# the JSON schema shown to the model AND parses back; populate_by_name keeps the
# snake_case usable in Python. model_dump(by_alias=True) → camelCase for the
# persistence layer (services.pipeline._persist_scenes reads visualType, etc.).
class GenCitation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: str
    source_span: str = Field(alias="sourceSpan")


class GenSeriesPoint(BaseModel):
    label: str
    value: float


class GenSceneParams(BaseModel):
    """Union of every visual type's params, all optional — a closed schema
    (no dict[str, Any]) so provider-native structured output works everywhere
    (Gemini rejects/mangles additionalProperties)."""

    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None  # title.card
    subtitle: str | None = None  # title.card
    bullets: list[str] | None = None  # bullet.reveal
    caption: str | None = None  # figure.callout
    figure_ref: str | None = Field(default=None, alias="figureRef")  # figure.callout
    latex: str | None = None  # equation.build
    series: list[GenSeriesPoint] | None = None  # dataviz.bar
    tokens: list[str] | None = None  # diagram.attention
    left: str | None = None  # comparison.split
    right: str | None = None  # comparison.split
    text: str | None = None  # kinetic.type


class GenScene(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Optional: with TTS off the designer is told narration may be omitted.
    narration: str = ""
    visual_type: VisualType = Field(alias="visualType")
    params: GenSceneParams = Field(default_factory=GenSceneParams)
    caption_style: CaptionStyle = Field(default=CaptionStyle.MINIMAL, alias="captionStyle")
    transition: SceneTransition = SceneTransition.FADE
    duration_ms: int = Field(default=6000, alias="durationMs")
    citations: list[GenCitation] = Field(default_factory=list)

    @field_validator("duration_ms", mode="after")
    @classmethod
    def _clamp_duration(cls, v: int) -> int:
        return min(max(v, 1000), 60_000)


class GenDocument(BaseModel):
    scenes: list[GenScene]


# ── Verifier schema (structured output; no tools → provider-native) ───────────
class GenVerifierFlag(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    claim: str
    source_span: str = Field(alias="sourceSpan")
    level: Literal["pass", "warn", "fail"]
    note: str | None = None


class VerifierReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    approved: bool
    flags: list[GenVerifierFlag] = Field(default_factory=list)
    # What the designer must change when not approved.
    revision_notes: str = Field(default="", alias="revisionNotes")


_DESIGNER_INSTRUCTIONS = [
    "You are the visual designer for Vyakhya, which turns research papers into "
    "editable explainer videos rendered by HyperFrames.",
    "Read the HyperFrames skills (call get_skill_instructions for 'hyperframes-core' "
    "and 'faceless-explainer') before designing, so your scenes follow the authoring "
    "contract.",
    "Produce an ordered list of scenes that explains the paper section by section. "
    "Use ONLY these visual types and their params: "
    "title.card {title, subtitle}; bullet.reveal {bullets: string[]}; "
    "figure.callout {caption, figureRef}; equation.build {latex}; "
    "dataviz.bar {series: [{label, value}]}; diagram.attention {tokens: string[]}; "
    "comparison.split {left, right}; kinetic.type {text}.",
    "params keys MUST match the scene's visualType exactly (e.g. kinetic.type uses "
    "`text`, never `tokens`; diagram.attention uses `tokens`, never `caption`) — a "
    "scene with params under the wrong key renders as a BLANK frame.",
    "Every scene needs at least one citation grounding it to a source span in the "
    "paper (e.g. '§3.2, p. 4').",
]


_VERIFIER_INSTRUCTIONS = [
    "You are the verifier for Vyakhya. You receive the paper text and the designed "
    "scenes (JSON). Check every factual claim in the scenes' narration and on-screen "
    "text against the paper.",
    "Report one flag per checked claim: level 'pass' when grounded, 'warn' when "
    "plausible but not clearly supported, 'fail' when contradicted or invented. "
    "sourceSpan is where in the paper you checked (e.g. '§3.2, p. 4').",
    "Also fail scenes whose citations don't point at real content in the paper.",
    "Set approved=true ONLY when there are no 'fail' flags. When not approved, put "
    "concrete, actionable fixes in revisionNotes (which scene, what to change).",
]

# Verify → revise loop bound: up to N verification rounds (N-1 designer revisions).
_MAX_VERIFY_ROUNDS = 3

# Final cut must land within this fraction of the requested length.
_DURATION_TOLERANCE = 0.15


def _length_instruction(target_min: int, tts: bool) -> str:
    target_ms = max(1, target_min) * 60_000
    per = "4000–9000 ms"
    n_lo = max(3, target_ms // 9000)
    n_hi = max(n_lo + 2, target_ms // 4000)
    narration = (
        "Every scene needs narration (what the voice-over says)."
        if tts
        else "Narration is optional (no voice-over); keep any narration terse as on-screen text."
    )
    return (
        f"The video should total about {target_ms} ms ({target_min} min). Size the scene "
        f"count and per-scene durations to reach that total — roughly {n_lo}–{n_hi} scenes at "
        f"{per} each. Do not stop at a handful of scenes if the target is long. {narration}"
    )


async def _resolve_llm_connection(
    session: Any,
) -> tuple[ProviderConnection, str] | None:
    """Pick the visual-designer's LLM connection (or any LLM one) + decrypt key."""
    assignment = await session.get(AgentModelAssignment, "visual_designer")
    conn: ProviderConnection | None = None
    if assignment is not None and assignment.connection_id:
        conn = await session.get(ProviderConnection, assignment.connection_id)
    if conn is None or conn.kind != ProviderKind.LLM:
        result = await session.execute(
            select(ProviderConnection)
            .where(ProviderConnection.kind == ProviderKind.LLM)
            .order_by(ProviderConnection.created_at)
        )
        conn = result.scalars().first()
    if conn is None:
        return None
    api_key = ""
    if conn.api_key_enc is not None:
        api_key = (await get_encryptor(session)).decrypt(conn.api_key_enc)
    return conn, api_key


async def _load_paper_text(project: Project) -> str:
    """The paper's text for the agent's context: prefer the text extracted at
    upload time, fall back to fetching paper_file_url, then title-only."""
    if project.paper_text:
        return project.paper_text[:60_000]
    url = project.paper_file_url
    if not url:
        return f"(No PDF text available. Title: {project.title}.)"
    try:
        import io

        from pypdf import PdfReader

        if url.startswith("s3://"):
            from vyakhya.services import storage

            content = await storage.get_object(url)
        else:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            content = resp.content

        reader = PdfReader(io.BytesIO(content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return text[:60_000] or f"(Empty PDF. Title: {project.title}.)"
    except Exception as exc:  # noqa: BLE001 - degrade gracefully to title-only
        log.warning("paper text extraction failed for %s: %s", project.id, exc)
        return f"(Could not read PDF: {exc}. Title: {project.title}.)"


def _extract_data(content: object) -> dict | list | None:
    """Get a plain dict/list out of whatever Agno returned (model instance,
    dict, or raw/fenced JSON string)."""
    if isinstance(content, BaseModel):
        return content.model_dump(by_alias=True)
    if isinstance(content, dict | list):
        return content
    if isinstance(content, str):
        import json
        import re

        text = content.strip()
        fence = re.search(r"```(?:json)?\s*([\[{].*[\]}])\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        try:
            return json.loads(text)
        except Exception:  # noqa: BLE001
            # Last resort: grab the outermost JSON object in the text.
            brace = re.search(r"\{.*\}", text, re.DOTALL)
            if brace:
                try:
                    return json.loads(brace.group(0))
                except Exception:  # noqa: BLE001
                    return None
            return None
    return None


def _coerce_document(content: object) -> GenDocument | None:
    """Normalize the agent output to a GenDocument, salvaging what validates:
    a whole-document parse first, then scene-by-scene (invalid scenes dropped)."""
    if isinstance(content, GenDocument):
        return content
    data = _extract_data(content)
    if data is None:
        return None
    if isinstance(data, list):  # bare scene array without the {"scenes": ...} wrapper
        data = {"scenes": data}
    try:
        return GenDocument.model_validate(data)
    except Exception:  # noqa: BLE001 - fall through to per-scene salvage
        pass
    raw_scenes = data.get("scenes")
    if not isinstance(raw_scenes, list):
        return None
    scenes: list[GenScene] = []
    for i, raw in enumerate(raw_scenes):
        try:
            scenes.append(GenScene.model_validate(raw))
        except Exception as exc:  # noqa: BLE001 - drop just this scene
            log.warning("dropping invalid scene %d: %s", i, exc)
    if not scenes:
        return None
    return GenDocument(scenes=scenes)


def _normalize_scene_params(scene: GenScene) -> None:
    """Repair params the model filed under a sibling key — e.g. kinetic.type
    with `tokens` instead of `text` — so every visual renders non-blank."""
    p = scene.params
    vt = scene.visual_type
    if vt is VisualType.KINETIC_TYPE and not p.text:
        p.text = " ".join(p.tokens) if p.tokens else (p.title or p.caption or scene.narration[:80])
    elif vt is VisualType.DIAGRAM_ATTENTION and not p.tokens:
        source = p.caption or p.text or scene.narration
        p.tokens = p.bullets or (source.split()[:8] if source else None)
    elif vt is VisualType.BULLET_REVEAL and not p.bullets:
        p.bullets = p.tokens
    elif vt is VisualType.TITLE_CARD and not p.title:
        p.title = p.text or p.caption or scene.narration[:60]
    elif vt is VisualType.FIGURE_CALLOUT and not p.caption:
        p.caption = p.text or p.title
    elif vt is VisualType.EQUATION_BUILD and not p.latex:
        p.latex = p.text
    elif vt is VisualType.COMPARISON_SPLIT and not (p.left and p.right):
        if p.bullets and len(p.bullets) >= 2:
            p.left, p.right = p.left or p.bullets[0], p.right or p.bullets[1]


def _dump_scenes(doc: GenDocument) -> list[dict]:
    for s in doc.scenes:
        _normalize_scene_params(s)
    return [s.model_dump(by_alias=True, exclude_none=True) for s in doc.scenes]


def _scenes_json(doc: GenDocument) -> str:
    import json

    return json.dumps(
        [s.model_dump(by_alias=True, exclude_none=True) for s in doc.scenes], indent=1
    )


class AgnoPipelineExecutor:
    """Real Agno crew. Emits the same events as the simulated executor."""

    async def run(self, project_id: str) -> AsyncIterator[dict]:  # noqa: C901
        from agno.agent import Agent

        sm = get_sessionmaker()
        async with sm() as session:
            project = await session.get(Project, project_id)
            if project is None:
                raise RuntimeError(f"project {project_id} not found")
            title = project.title
            audience = project.audience
            language = project.language
            target_min = project.target_length_min or 3
            tts_enabled = project.tts_enabled
            resolved = await _resolve_llm_connection(session)
            if resolved is None:
                yield _event(
                    PipelineEventType.LOG,
                    "No LLM connection configured — add one in Model Config.",
                    AgentId.INGESTOR,
                )
                raise RuntimeError("no LLM connection configured for the Agno pipeline")
            conn, api_key = resolved
            paper_text = await _load_paper_text(project)

        if paper_text.startswith("("):
            yield _event(
                PipelineEventType.LOG,
                "Paper text unavailable — the designer only has the title to work from.",
                AgentId.INGESTOR,
            )

        model = build_llm_model(conn.provider, conn.model, api_key, conn.base_url)
        parser = build_llm_model(conn.provider, conn.model, api_key, conn.base_url)
        skills = get_hyperframes_skills()
        designer = Agent(
            name="Visual Designer",
            model=model,
            skills=skills,
            instructions=[*_DESIGNER_INSTRUCTIONS, _length_instruction(target_min, tts_enabled)],
            output_schema=GenDocument,
            # The designer keeps its skill tools; a separate parser pass (no
            # tools) converts its answer via provider-native structured output.
            # This avoids the "json mode + tool calling" conflict AND the
            # schema-drift failures of prompt-injected JSON mode.
            parser_model=parser,
            markdown=False,
        )
        verifier = Agent(
            name="Verifier",
            model=build_llm_model(conn.provider, conn.model, api_key, conn.base_url),
            instructions=_VERIFIER_INSTRUCTIONS,
            # No tools → provider-native structured output directly.
            output_schema=VerifierReport,
            markdown=False,
        )

        total = len(AGENT_SEQUENCE)
        scenes_payload: list[dict] = []
        doc: GenDocument | None = None

        for idx, (agent_id, label) in enumerate(AGENT_SEQUENCE):
            yield _event(PipelineEventType.STATUS, AgentStatus.RUNNING.value, agent_id)
            yield _event(PipelineEventType.LOG, f"[{label}] working…", agent_id)

            if agent_id is AgentId.VISUAL_DESIGNER:
                prompt = (
                    f"Design the explainer scenes for this paper.\n"
                    f"Title: {title}\nAudience: {AudienceLevel(audience).value}\n"
                    f"Language: {language}\n\nPaper text:\n{paper_text}"
                )
                last_error = "model returned no parseable scenes"
                for attempt in range(2):
                    try:
                        result = await designer.arun(input=prompt, stream=False)
                    except Exception as exc:  # noqa: BLE001 - provider hiccup → retry once
                        last_error = f"model call failed: {exc}"
                        log.warning("designer attempt %d failed: %s", attempt + 1, exc)
                        continue
                    doc = _coerce_document(result.content if result else None)
                    if doc is not None and doc.scenes:
                        break
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] attempt {attempt + 1} produced no valid scenes, retrying…",
                        agent_id,
                    )
                    prompt += (
                        "\n\nIMPORTANT: your previous answer did not match the required "
                        "schema. Respond with ONLY a JSON object of the form "
                        '{"scenes": [{"narration", "visualType", "params", "captionStyle", '
                        '"transition", "durationMs", "citations"}, ...]} — no prose.'
                    )
                if doc is None or not doc.scenes:
                    yield _event(PipelineEventType.LOG, f"[{label}] {last_error}", agent_id)
                    yield _event(PipelineEventType.STATUS, AgentStatus.ERROR.value, agent_id)
                    raise RuntimeError(f"visual designer produced no scenes ({last_error})")
                scenes_payload = _dump_scenes(doc)
                yield _event(
                    PipelineEventType.LOG,
                    f"[{label}] produced {len(scenes_payload)} scenes",
                    agent_id,
                )

            if agent_id is AgentId.VERIFIER and doc is not None:
                # Agentic verify → revise loop: the verifier grounds every claim
                # in the paper; on failure the designer revises and the verifier
                # re-checks, up to _MAX_VERIFY_ROUNDS rounds.
                for round_no in range(1, _MAX_VERIFY_ROUNDS + 1):
                    report: VerifierReport | None = None
                    try:
                        vres = await verifier.arun(
                            input=(
                                f"Verify these scenes against the paper.\n\n"
                                f"Scenes:\n{_scenes_json(doc)}\n\nPaper text:\n{paper_text}"
                            ),
                            stream=False,
                        )
                        content = vres.content if vres else None
                        if isinstance(content, VerifierReport):
                            report = content
                        else:
                            data = _extract_data(content)
                            if isinstance(data, dict):
                                report = VerifierReport.model_validate(data)
                    except Exception as exc:  # noqa: BLE001 - verification is best-effort
                        log.warning("verifier round %d failed: %s", round_no, exc)
                    if report is None:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] round {round_no}: verifier unavailable — "
                            "proceeding without verification",
                            agent_id,
                        )
                        break
                    for flag in report.flags:
                        payload = flag.model_dump(by_alias=True)
                        payload["id"] = new_id("vf")
                        yield _event(PipelineEventType.FLAG, payload, agent_id)
                    fails = [f for f in report.flags if f.level == "fail"]
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] round {round_no}: {len(report.flags)} claims checked, "
                        f"{len(fails)} failed",
                        agent_id,
                    )
                    if report.approved and not fails:
                        yield _event(PipelineEventType.LOG, f"[{label}] approved", agent_id)
                        break
                    if round_no == _MAX_VERIFY_ROUNDS:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] max revision rounds reached — proceeding with "
                            f"{len(fails)} unresolved flag(s)",
                            agent_id,
                        )
                        break
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] sending scenes back to the designer for revision…",
                        agent_id,
                    )
                    fail_lines = "\n".join(
                        f"- {f.claim} ({f.source_span}): {f.note or f.level}"
                        for f in report.flags
                        if f.level != "pass"
                    )
                    revision_prompt = (
                        f"Revise your scenes. The verifier rejected them.\n\n"
                        f"Verifier notes:\n{report.revision_notes}\n\n"
                        f"Flagged claims:\n{fail_lines}\n\n"
                        f"Current scenes:\n{_scenes_json(doc)}\n\n"
                        f"Fix ONLY what the verifier flagged (keep everything else), "
                        f"grounding every claim in the paper.\n\nPaper text:\n{paper_text}"
                    )
                    try:
                        rres = await designer.arun(input=revision_prompt, stream=False)
                        revised = _coerce_document(rres.content if rres else None)
                    except Exception as exc:  # noqa: BLE001 - keep current doc on failure
                        log.warning("designer revision failed: %s", exc)
                        revised = None
                    if revised is not None and revised.scenes:
                        doc = revised
                        scenes_payload = _dump_scenes(doc)
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] designer revised → {len(doc.scenes)} scenes",
                            agent_id,
                        )
                    else:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] revision produced no valid scenes — keeping current cut",
                            agent_id,
                        )

            if agent_id is AgentId.ASSEMBLER and doc is not None:
                # Agentic length fit: when the cut misses the requested length,
                # the DESIGNER fixes it — adding grounded scenes when short,
                # merging/trimming when long. Never a mechanical rescale.
                target_ms = max(1, target_min) * 60_000
                for fit_round in range(1, 3):
                    total_ms = sum(s.duration_ms for s in doc.scenes)
                    deviation = abs(total_ms - target_ms) / target_ms
                    if deviation <= _DURATION_TOLERANCE:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] cut is {total_ms / 1000:.0f}s — within tolerance "
                            f"of the {target_min} min target",
                            agent_id,
                        )
                        break
                    direction = (
                        "too SHORT — add new scenes covering more of the paper "
                        "(each grounded with citations), or deepen existing ones"
                        if total_ms < target_ms
                        else "too LONG — merge or drop the least important scenes"
                    )
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] cut is {total_ms / 1000:.0f}s vs {target_ms / 1000:.0f}s "
                        f"target ({direction.split(' — ')[0]}) — asking the designer to fix",
                        agent_id,
                    )
                    fit_prompt = (
                        f"Your scene list totals {total_ms} ms but the video must total "
                        f"about {target_ms} ms. It is {direction}. Keep every verified "
                        f"scene's content intact where possible and return the FULL "
                        f"revised scene list.\n\nCurrent scenes:\n{_scenes_json(doc)}\n\n"
                        f"Paper text:\n{paper_text}"
                    )
                    try:
                        fres = await designer.arun(input=fit_prompt, stream=False)
                        fixed = _coerce_document(fres.content if fres else None)
                    except Exception as exc:  # noqa: BLE001 - keep current cut
                        log.warning("length-fit round %d failed: %s", fit_round, exc)
                        fixed = None
                    if fixed is None or not fixed.scenes:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] length fix produced no valid scenes — keeping cut",
                            agent_id,
                        )
                        break
                    doc = fixed
                    scenes_payload = _dump_scenes(doc)
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] designer adjusted → {len(doc.scenes)} scenes, "
                        f"{sum(s.duration_ms for s in doc.scenes) / 1000:.0f}s",
                        agent_id,
                    )

            yield _event(PipelineEventType.STATUS, AgentStatus.DONE.value, agent_id)
            yield _event(PipelineEventType.PROGRESS, round((idx + 1) / total, 3))

            if agent_id is AgentId.ASSEMBLER and scenes_payload:
                yield _event(PipelineEventType.SCENES, scenes_payload, agent_id)

        yield _event(PipelineEventType.DONE, None)
