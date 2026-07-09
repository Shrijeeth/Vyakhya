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
from vyakhya.agents.skills import get_designer_skill_text
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
    figure_id: str | None = Field(default=None, alias="figureId")  # figure.callout (fig1, fig2…)
    figure_url: str | None = Field(default=None, alias="figureUrl")  # resolved by the pipeline
    latex: str | None = None  # equation.build
    series: list[GenSeriesPoint] | None = None  # dataviz.bar
    tokens: list[str] | None = None  # diagram.attention + orbit.3d
    left: str | None = None  # comparison.split
    right: str | None = None  # comparison.split
    text: str | None = None  # kinetic.type
    # custom.html — agent-authored stage markup + styles (no scripts).
    html: str | None = None
    css: str | None = None
    # Narration audio, attached by the pipeline (never by the model): the
    # compiler turns audioUrl into an <audio class="clip"> on track 10.
    audio_url: str | None = Field(default=None, alias="audioUrl")
    audio_duration_ms: int | None = Field(default=None, alias="audioDurationMs")


class GenScene(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # 0-based position — used by revision replies to patch scenes in place
    # (revisions return ONLY changed scenes, never the whole list).
    index: int | None = None
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

    # Cosmetic enums must never kill a scene: models invent values like
    # captionStyle "mono-lower-third" — coerce to the default instead.
    @field_validator("caption_style", mode="before")
    @classmethod
    def _lenient_caption(cls, v: object) -> object:
        try:
            return CaptionStyle(v)  # type: ignore[arg-type]
        except ValueError:
            return CaptionStyle.MINIMAL

    @field_validator("transition", mode="before")
    @classmethod
    def _lenient_transition(cls, v: object) -> object:
        try:
            return SceneTransition(v)  # type: ignore[arg-type]
        except ValueError:
            return SceneTransition.FADE


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


# ── Visual design review (vision: per-scene screenshots) ──────────────────────
class DesignIssue(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scene_index: int = Field(alias="sceneIndex")
    problem: str
    fix: str
    severity: Literal["minor", "major"] = "major"


class DesignReviewReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    approved: bool
    issues: list[DesignIssue] = Field(default_factory=list)


# ── Story plan (planner stage; escalation target when a cut goes wrong) ───────
class PlanBeat(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # When replacing an existing scene (verifier escalation), the 0-based
    # index of the scene this beat replaces; None for brand-new beats.
    index: int | None = None
    headline: str
    summary: str = ""
    duration_ms: int = Field(default=9000, alias="durationMs")


class StoryPlan(BaseModel):
    beats: list[PlanBeat] = Field(default_factory=list)


_PLANNER_INSTRUCTIONS = [
    "You are the story planner for Vyakhya: it turns any document into an "
    "explainer video. You write the beat sheet the visual designer designs "
    "one scene per beat from.",
    "THE USER BRIEF IS LAW. If it asks for a story, plan a story arc; if it "
    "says layman, plan for a layman. Its structure, tone, and style override "
    "everything else here.",
    "Cover the document end to end: a hook, the build-up through the "
    "document's key ideas, the payoff, and a closer. Every beat's summary "
    "names the part of the document it draws from.",
    "Respect the requested beat count and total duration — a long video "
    "needs MANY beats, not a handful of long ones.",
]


_DESIGN_REVIEWER_INSTRUCTIONS = [
    "You are the art director reviewing RENDERED SCREENSHOTS of an explainer "
    "video's scenes (one image per scene, in order). Judge what you SEE.",
    "REJECT a scene (severity major) when: elements overlap illegibly (text on "
    "top of images or other text), content is clipped/offscreen, the frame is "
    "empty or near-empty, text is tiny/unstyled, contrast is poor, the default "
    "cream background shows instead of the project's theme, or the scene is an "
    "incomplete visualization (a bare sentence with no visual structure).",
    "Also flag (minor) blandness and doctrine violations: plain centered text "
    "where a richer composition (diagram, split layout, big-number, figure "
    "panel) fits, full narration sentences printed on screen instead of short "
    "motion-graphics copy, the same framing repeated in adjacent scenes, a "
    "primary visual owning well under 40% of the canvas, or generic "
    "purple-blue AI-gradient styling.",
    "For each issue give the scene index (0-based, matching image order), what "
    "is wrong VISUALLY, and a concrete CSS/layout fix the designer can apply.",
    "Set approved=true ONLY when there are no major issues.",
]

# Deliberately lean: the USER BRIEF and the HyperFrames skills carry the
# creative direction; the vision reviewer enforces visual quality. Piling
# doctrine here dilutes the brief and flattens creativity.
_DESIGNER_INSTRUCTIONS = [
    "You are the visual designer for Vyakhya: it turns any document into an "
    "explainer video rendered by HyperFrames.",
    "THE USER BRIEF IS LAW. If it asks for a story, tell a story; if it says "
    "layman, write for a layman. Its structure, tone, and style override "
    "everything else here.",
    "Design like the HyperFrames authoring guides included below: rich "
    "compositions — diagrams, CSS 3D (perspective/rotate3d), charts drawn "
    "with divs/SVG, big numbers, figure panels — not text slides.",
    "Every scene is visualType custom.html with params {html, css}: you author "
    "the full 1920x1080 frame, with a themed background (never the default). "
    "Use the provided figures via their exact <img> URLs; never invent URLs.",
    "Hard contract: no <script>; every class you use is defined in the css "
    "param (slug-prefixed per scene); animations are finite with fill-mode "
    "both and delays written as calc(var(--t0, 0s) + <offset>); size with % "
    "(vh/vw are the browser viewport, not the frame); give empty decorative "
    "divs explicit width and height; lay out with flexbox/grid so nothing "
    "overlaps; keep text large and high-contrast.",
    "Narration carries the explanation (~2.7 words/sec — size durationMs to "
    "it); on-screen text stays short and punchy.",
    "Every scene cites a real span of the document (e.g. '§3.2, p. 4').",
    'Your final message is ONLY a JSON object {"scenes": [{"narration", '
    '"visualType", "params": {"html", "css"}, "captionStyle", "transition", '
    '"durationMs", "citations": [{"label", "sourceSpan"}]}, ...]} — no prose, '
    "no markdown fences.",
]


_RESEARCHER_INSTRUCTIONS = [
    "You are the comprehension researcher for Vyakhya. Given a document's title "
    "and opening, use your web tools (search, Wikipedia) to gather context that "
    "helps explain it to the target audience: background it builds on, real-world "
    "impact, common misconceptions, and simple analogies.",
    "Be fast: at most 3-4 tool calls. Return concise, factual notes — no filler.",
]


class ResearchNotes(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    summary: str = ""
    key_points: list[str] = Field(default_factory=list, alias="keyPoints")
    analogies: list[str] = Field(default_factory=list)


def _research_tools() -> list[Any]:
    """Web tools for the researcher, skipping any whose deps are missing."""
    tools: list[Any] = []
    try:
        from agno.tools.duckduckgo import DuckDuckGoTools

        tools.append(DuckDuckGoTools())
    except Exception as exc:  # noqa: BLE001 - optional dep
        log.warning("DuckDuckGo tools unavailable: %s", exc)
    try:
        from agno.tools.wikipedia import WikipediaTools

        tools.append(WikipediaTools())
    except Exception as exc:  # noqa: BLE001 - optional dep
        log.warning("Wikipedia tools unavailable: %s", exc)
    return tools


_VERIFIER_INSTRUCTIONS = [
    "You are the verifier for Vyakhya. You receive the source document's text and "
    "the designed scenes (JSON). Check every factual claim in the scenes' narration "
    "and on-screen text against the document.",
    "Report one flag per checked claim: level 'pass' when grounded, 'warn' when "
    "plausible but not clearly supported, 'fail' when contradicted or invented. "
    "sourceSpan is where in the document you checked (e.g. '§3.2, p. 4').",
    "Also fail scenes whose citations don't point at real content in the document.",
    "Set approved=true ONLY when there are no 'fail' flags. When not approved, put "
    "concrete, actionable fixes in revisionNotes (which scene, what to change).",
]

# Final cut must land within this fraction of the requested length.
_DURATION_TOLERANCE = 0.15

# Beats per designer call. Scene JSON is heavy (~1.5k output tokens of
# html+css per scene); more than this per completion risks truncation.
_SCENE_BATCH = 6


def _brief_block(user_prompt: str) -> str:
    """The user's creative brief, prepended to EVERY designer prompt (initial
    and all revisions) so it is never diluted by later feedback."""
    if not user_prompt:
        return ""
    return (
        "USER BRIEF — HIGHEST PRIORITY, overrides all defaults. Follow its "
        "story structure, tone, and style in every scene:\n"
        f"{user_prompt}\n\n"
    )


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


async def _resolve_role_connection(
    session: Any, role: str
) -> tuple[ProviderConnection, str] | None:
    """The LLM connection explicitly assigned to a role (no fallback)."""
    assignment = await session.get(AgentModelAssignment, role)
    if assignment is None or not assignment.connection_id:
        return None
    conn = await session.get(ProviderConnection, assignment.connection_id)
    if conn is None or conn.kind != ProviderKind.LLM:
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


def _salvage_scene_objects(text: str) -> list | None:
    """Recover complete scene objects from a TRUNCATED response (the model
    hit its output-token cap mid-JSON): decode objects one by one from the
    "scenes" array and drop the incomplete tail."""
    import json
    import re

    m = re.search(r'"scenes"\s*:\s*\[', text)
    start = m.end() if m else (text.find("[") + 1 if text.lstrip().startswith("[") else -1)
    if start <= 0:
        return None
    dec = json.JSONDecoder()
    idx, n, out = start, len(text), []
    while idx < n:
        while idx < n and text[idx] in " \t\r\n,":
            idx += 1
        if idx >= n or text[idx] == "]":
            break
        try:
            obj, idx = dec.raw_decode(text, idx)
        except Exception:  # noqa: BLE001 - truncation point reached
            break
        out.append(obj)
    return out or None


def _coerce_document(content: object) -> GenDocument | None:
    """Normalize the agent output to a GenDocument, salvaging what validates:
    a whole-document parse first, then scene-by-scene (invalid scenes dropped)."""
    if isinstance(content, GenDocument):
        return content
    data = _extract_data(content)
    if data is None and isinstance(content, str):
        # Truncated JSON (output-token cap): keep every complete scene.
        salvaged = _salvage_scene_objects(content)
        if salvaged:
            log.warning("response truncated — salvaged %d complete scene(s)", len(salvaged))
            data = {"scenes": salvaged}
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


def _coerce_plan(content: object) -> StoryPlan | None:
    """Normalize planner output to a StoryPlan (model, dict, or bare beat list)."""
    if isinstance(content, StoryPlan):
        return content if content.beats else None
    data = _extract_data(content)
    if isinstance(data, list):
        data = {"beats": data}
    if not isinstance(data, dict):
        return None
    try:
        plan = StoryPlan.model_validate(data)
    except Exception:  # noqa: BLE001 - a bad plan is just skipped
        return None
    return plan if plan.beats else None


def _plan_block(plan: StoryPlan | None) -> str:
    """The beat sheet, appended to the designer's initial prompt."""
    if plan is None or not plan.beats:
        return ""
    lines = "\n".join(
        f"{i}: {b.headline} — {b.summary} (~{b.duration_ms} ms)" for i, b in enumerate(plan.beats)
    )
    return f"\n\nStory plan — design ONE scene per beat, in order (durations are guides):\n{lines}"


def _patch_scenes(doc: GenDocument, revised: GenDocument) -> int:
    """Apply a partial revision: each revised scene replaces the scene at its
    0-based ``index``. Returns how many were patched. A reply without indexes
    is applied wholesale ONLY when it is the same size as the current cut —
    a shorter unindexed reply is a truncated/partial list, never a new cut."""
    indexed = [sc for sc in revised.scenes if sc.index is not None]
    if indexed:
        patched = 0
        for sc in indexed:
            if 0 <= sc.index < len(doc.scenes):
                doc.scenes[sc.index] = sc
                patched += 1
        return patched
    if len(revised.scenes) >= len(doc.scenes):
        doc.scenes = revised.scenes
        return len(revised.scenes)
    return 0


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
    elif vt is VisualType.ORBIT_3D and not p.tokens:
        source = p.title or p.text or p.caption or scene.narration
        p.tokens = p.bullets or (source.split()[:6] if source else None)
    elif vt is VisualType.CUSTOM_HTML:
        html = p.html or ""
        # A custom scene must be self-styled: markup with bare classes and no
        # css/inline styles renders as tiny unstyled text. Degrade those (and
        # empty ones) to a kinetic text card instead of shipping a broken frame.
        unstyled = "class=" in html and not p.css and "style=" not in html
        if not html.strip() or unstyled:
            scene.visual_type = VisualType.KINETIC_TYPE
            import re as _re

            plain = _re.sub(r"<[^>]+>", " ", html).strip()
            p.text = p.text or plain[:80] or p.title or p.caption or scene.narration[:80]


def _dump_scenes(doc: GenDocument, figure_map: dict[str, str] | None = None) -> list[dict]:
    fmap = figure_map or {}
    for s in doc.scenes:
        _normalize_scene_params(s)
        # Resolve figureId → the cropped figure's URL (never trust invented ids).
        p = s.params
        if p.figure_id:
            url = fmap.get(p.figure_id)
            p.figure_url = url
            if url is None:
                p.figure_id = None
    # The model often writes figure.callout without figureId — assign the
    # extracted figures in document order so real crops appear regardless.
    used = {s.params.figure_id for s in doc.scenes if s.params.figure_id}
    unused = [(fid, url) for fid, url in fmap.items() if fid not in used]
    for s in doc.scenes:
        if s.visual_type is VisualType.FIGURE_CALLOUT and not s.params.figure_url and unused:
            fid, url = unused.pop(0)
            s.params.figure_id, s.params.figure_url = fid, url
    return [s.model_dump(by_alias=True, exclude_none=True) for s in doc.scenes]


def _screenshot_doc(project_id: str, title: str, aspect: str, scenes_payload: list[dict]) -> dict:
    """Scene-JSON the render service can compile for review screenshots."""
    return {
        "id": project_id,
        "title": title,
        "aspectRatio": aspect,
        "scenes": [{"id": f"rev{i}", **s, "index": i} for i, s in enumerate(scenes_payload)],
    }


async def _review_images(shot_doc: dict) -> list[Any]:
    """Screenshots of every scene as Agno images for the vision reviewer."""
    import base64

    from agno.media import Image as AgnoImage

    from vyakhya.services.render_client import capture_scene_screenshots

    shots = await capture_scene_screenshots(shot_doc)
    return [
        AgnoImage(content=base64.b64decode(s["png"]), format="png")
        for s in shots
        if isinstance(s.get("png"), str)
    ]


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
            aspect = project.aspect_ratio.value
            user_prompt = (project.user_prompt or "").strip()
            figures: list[dict] = list(project.figures or [])
            paper_file_url = project.paper_file_url
            from vyakhya.services.connections import get_agent_settings

            aset = await get_agent_settings(session)
            verifier_rounds = aset.verifier_max_rounds
            visual_max_rounds = aset.visual_max_rounds
            visual_stall_rounds = aset.visual_stall_rounds
            length_fit_rounds = aset.length_fit_rounds
            resolved = await _resolve_llm_connection(session)
            if resolved is None:
                yield _event(
                    PipelineEventType.LOG,
                    "No LLM connection configured — add one in Model Config.",
                    AgentId.INGESTOR,
                )
                raise RuntimeError("no LLM connection configured for the Agno pipeline")
            conn, api_key = resolved
            parser_resolved = await _resolve_role_connection(session, "parser")
            # Honor the Model Config role assignments for every agent (not
            # just the designer): unassigned roles fall back to the main
            # (visual designer) connection.
            role_conns = {
                role: await _resolve_role_connection(session, role)
                for role in ("comprehension", "planner", "verifier")
            }
            paper_text = await _load_paper_text(project)

        if paper_text.startswith("("):
            yield _event(
                PipelineEventType.LOG,
                "Paper text unavailable — the designer only has the title to work from.",
                AgentId.INGESTOR,
            )

        model = build_llm_model(conn.provider, conn.model, api_key, conn.base_url, conn.settings)

        # Every agent gets structured output via a parser_model pass. The
        # parser is its own role in Model Config — assign a FAST model there
        # (its whole job is converting an answer to schema JSON); unassigned,
        # it falls back to the main connection's model.
        pconn, pkey = parser_resolved if parser_resolved is not None else (conn, api_key)
        log.info("parser model: %s/%s", pconn.provider.value, pconn.model)

        def _parser_model() -> Any:
            return build_llm_model(
                pconn.provider, pconn.model, pkey, pconn.base_url, pconn.settings
            )

        def _role_model(role: str) -> Any:
            rc = role_conns.get(role)
            c, k = rc if rc is not None else (conn, api_key)
            log.info("%s model: %s/%s", role, c.provider.value, c.model)
            return build_llm_model(c.provider, c.model, k, c.base_url, c.settings)

        designer = Agent(
            name="Visual Designer",
            model=model,
            # The HyperFrames guides are INLINED (no skills= tools): tool-based
            # skill loading costs 4-5 model round trips per call, while the
            # guides are only ~11k prompt tokens. One call in, one JSON out;
            # the parser pass (no tools) converts it via structured output.
            instructions=[
                *_DESIGNER_INSTRUCTIONS,
                _length_instruction(target_min, tts_enabled),
                get_designer_skill_text(),
            ],
            output_schema=GenDocument,
            parser_model=_parser_model(),
            markdown=False,
        )

        async def _design(prompt: str) -> GenDocument | None:
            """One designer call, timed; _coerce_document still guards the
            output (fence-stripping, truncation salvage, per-scene recovery).
            A provider failure (Agno swallows it into an errored run with no
            content) is raised so callers report the REAL cause instead of
            'no parseable scenes'."""
            import time as _time

            t0 = _time.monotonic()
            res = await designer.arun(input=prompt, stream=False)
            log.info("designer call took %.1fs", _time.monotonic() - t0)
            content = res.content if res else None
            if content is None:
                status = getattr(res, "status", None)
                status = str(getattr(status, "value", status) or "").lower()
                if res is None or status == "error":
                    raise RuntimeError(
                        "model call failed"
                        + (
                            f": {getattr(res, 'error', None)}"
                            if getattr(res, "error", None)
                            else ""
                        )
                        + " (see worker logs)"
                    )
            return _coerce_document(content)

        verifier = Agent(
            name="Verifier",
            model=_role_model("verifier"),
            instructions=_VERIFIER_INSTRUCTIONS,
            output_schema=VerifierReport,
            parser_model=_parser_model(),
            markdown=False,
        )
        design_reviewer = Agent(
            name="Design Reviewer",
            # Shares the verifier role's connection (must be vision-capable).
            model=_role_model("verifier"),
            instructions=_DESIGN_REVIEWER_INSTRUCTIONS,
            output_schema=DesignReviewReport,
            parser_model=_parser_model(),
            markdown=False,
        )
        planner = Agent(
            name="Planner",
            model=_role_model("planner"),
            instructions=_PLANNER_INSTRUCTIONS,
            output_schema=StoryPlan,
            parser_model=_parser_model(),
            markdown=False,
        )
        researcher = Agent(
            name="Researcher",
            model=_role_model("comprehension"),
            tools=_research_tools(),
            instructions=_RESEARCHER_INSTRUCTIONS,
            output_schema=ResearchNotes,
            parser_model=_parser_model(),
            markdown=False,
        )

        total = len(AGENT_SEQUENCE)
        scenes_payload: list[dict] = []
        doc: GenDocument | None = None
        research: ResearchNotes | None = None
        plan: StoryPlan | None = None
        figure_map: dict[str, str] = {f["id"]: f["url"] for f in figures if f.get("url")}

        for idx, (agent_id, label) in enumerate(AGENT_SEQUENCE):
            yield _event(PipelineEventType.STATUS, AgentStatus.RUNNING.value, agent_id)
            yield _event(PipelineEventType.LOG, f"[{label}] working…", agent_id)

            if agent_id is AgentId.INGESTOR and not figures and paper_file_url:
                # Crop the paper's figures so the designer can put the real
                # plots/diagrams on screen (figure.callout with figureId).
                try:
                    from vyakhya.services import storage
                    from vyakhya.services.figures import extract_figures

                    pdf_bytes = await storage.get_object(paper_file_url)
                    figures = await extract_figures(project_id, pdf_bytes)
                    figure_map = {f["id"]: f["url"] for f in figures}
                    async with sm() as session:
                        proj = await session.get(Project, project_id)
                        if proj is not None:
                            proj.figures = figures
                            await session.commit()
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] extracted {len(figures)} figure(s) from the PDF",
                        agent_id,
                    )
                except Exception as exc:  # noqa: BLE001 - figures are an enhancement
                    log.warning("figure extraction failed: %s", exc)
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] figure extraction failed: {exc}",
                        agent_id,
                    )

            if agent_id is AgentId.COMPREHENSION and researcher.tools:
                # Web research (search + Wikipedia) for grounding context the
                # paper itself doesn't carry: impact, prior work, analogies.
                try:
                    rres = await researcher.arun(
                        input=(
                            f"Research context for explaining this document.\n"
                            f"Title: {title}\n\nOpening of the document:\n{paper_text[:3000]}"
                        ),
                        stream=False,
                    )
                    content = rres.content if rres else None
                    if isinstance(content, ResearchNotes):
                        research = content
                    else:
                        data = _extract_data(content)
                        if isinstance(data, dict):
                            research = ResearchNotes.model_validate(data)
                    if research is not None:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] gathered {len(research.key_points)} research "
                            f"note(s) from the web",
                            agent_id,
                        )
                except Exception as exc:  # noqa: BLE001 - research is best-effort
                    log.warning("web research failed: %s", exc)
                    yield _event(
                        PipelineEventType.LOG, f"[{label}] web research skipped: {exc}", agent_id
                    )

            if agent_id is AgentId.PLANNER:
                # Beat sheet sized to the target length — the designer builds
                # one scene per beat, so a thin plan (the main cause of short
                # cuts) is caught here, not three stages later.
                target_ms = max(1, target_min) * 60_000
                n_lo = max(3, target_ms // 9000)
                n_hi = max(n_lo + 2, target_ms // 4000)
                research_note = (
                    f"\n\nWeb research summary:\n{research.summary}"
                    if research is not None and research.summary
                    else ""
                )
                try:
                    pres = await planner.arun(
                        input=(
                            f"{_brief_block(user_prompt)}"
                            f"Plan the beat sheet for this explainer video.\n"
                            f"Title: {title}\nAudience: {AudienceLevel(audience).value}\n"
                            f"Target: about {target_ms} ms total — plan {n_lo}–{n_hi} beats "
                            f"of 4000–9000 ms each, summing to the target."
                            f"{research_note}\n\nDocument text:\n{paper_text}"
                        ),
                        stream=False,
                    )
                    plan = _coerce_plan(pres.content if pres else None)
                except Exception as exc:  # noqa: BLE001 - the designer can work planless
                    log.warning("planner failed: %s", exc)
                if plan is not None:
                    planned_ms = sum(b.duration_ms for b in plan.beats)
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] {len(plan.beats)} beats planned "
                        f"(~{planned_ms / 1000:.0f}s vs {target_ms / 1000:.0f}s target)",
                        agent_id,
                    )
                else:
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] no usable plan — the designer will structure the video itself",
                        agent_id,
                    )

            if agent_id is AgentId.VISUAL_DESIGNER:
                figures_block = ""
                if figures:
                    lines = "\n".join(
                        f"- {f['id']}: page {f['page']}, {f['width']}x{f['height']}px"
                        for f in figures
                    )
                    figures_block = (
                        f"\n\nFigures cropped from the document (embed via <img> with "
                        f"figureId):\n{lines}"
                    )
                research_block = ""
                if research is not None and (research.summary or research.key_points):
                    notes = "\n".join(f"- {p}" for p in research.key_points)
                    analogies = "\n".join(f"- {a}" for a in research.analogies)
                    research_block = f"\n\nWeb research context:\n{research.summary}\n{notes}" + (
                        f"\nAnalogies you may use:\n{analogies}" if analogies else ""
                    )
                last_error = "model returned no parseable scenes"
                if plan is not None and len(plan.beats) > _SCENE_BATCH:
                    # Batched generation: the full cut's JSON (scene html+css ×
                    # dozens of beats) cannot fit one completion — a 36-beat
                    # video is ~50k output tokens and WILL truncate. Design a
                    # few beats per call and append; a failed batch just leaves
                    # a shortfall the length fit / re-plan below repairs.
                    doc = GenDocument(scenes=[])
                    n_batches = (len(plan.beats) + _SCENE_BATCH - 1) // _SCENE_BATCH
                    dead_batches = 0
                    for start in range(0, len(plan.beats), _SCENE_BATCH):
                        chunk = plan.beats[start : start + _SCENE_BATCH]
                        batch_no = start // _SCENE_BATCH + 1
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] designing beats {start}–{start + len(chunk) - 1} "
                            f"(batch {batch_no}/{n_batches})…",
                            agent_id,
                        )
                        beat_lines = "\n".join(
                            f"- {b.headline} — {b.summary} (~{b.duration_ms} ms)" for b in chunk
                        )
                        prev_block = ""
                        if doc.scenes:
                            tail = "\n".join(
                                f"- {(s.narration or '')[:60]}" for s in doc.scenes[-3:]
                            )
                            prev_block = (
                                f"\n\nScenes designed so far end with:\n{tail}\n"
                                "Keep the SAME visual theme (background, palette, "
                                "typography) so the video feels continuous."
                            )
                        bprompt = (
                            f"{_brief_block(user_prompt)}"
                            f"Design scenes for ONLY these {len(chunk)} beats of the "
                            f"story plan (the other beats are designed separately — "
                            f"do not cover them). EXACTLY ONE scene per beat, in "
                            f"beat order, each sized to its beat's duration: return "
                            f'{len(chunk)} scenes as {{"scenes": [...]}} — never '
                            f"merge or summarize beats.\n"
                            f"Title: {title}\nAudience: {AudienceLevel(audience).value}\n"
                            f"Language: {language}{figures_block}{research_block}\n\n"
                            f"Beats:\n{beat_lines}{prev_block}\n\n"
                            f"Document text:\n{paper_text}"
                        )
                        batch: GenDocument | None = None
                        batch_err = ""
                        for attempt in range(2):
                            # One batch is one long NON-STREAMED model call
                            # (minutes on slow endpoints) — heartbeat events so
                            # the stream shows life, not a stuck stage.
                            import asyncio as _aio

                            dtask = _aio.ensure_future(_design(bprompt))
                            waited = 0
                            while True:
                                done, _ = await _aio.wait({dtask}, timeout=60)
                                if done:
                                    break
                                waited += 60
                                yield _event(
                                    PipelineEventType.LOG,
                                    f"[{label}] batch {batch_no}/{n_batches} still "
                                    f"generating… ({waited}s)",
                                    agent_id,
                                )
                            try:
                                batch = dtask.result()
                            except Exception as exc:  # noqa: BLE001 - retry once
                                batch_err = str(exc)
                                log.warning(
                                    "designer batch %d attempt %d failed: %s",
                                    batch_no,
                                    attempt + 1,
                                    exc,
                                )
                                continue
                            if batch is not None and batch.scenes:
                                break
                        if batch is not None and batch.scenes:
                            dead_batches = 0
                            for sc in batch.scenes:
                                sc.index = None  # appended, never patched
                            doc.scenes.extend(batch.scenes)
                            yield _event(
                                PipelineEventType.LOG,
                                f"[{label}] batch {batch_no}/{n_batches} → "
                                f"{len(batch.scenes)} scene(s), {len(doc.scenes)} total",
                                agent_id,
                            )
                        else:
                            last_error = batch_err or "model returned no parseable scenes"
                            dead_batches += 1
                            yield _event(
                                PipelineEventType.LOG,
                                f"[{label}] batch {batch_no}/{n_batches} produced no "
                                f"valid scenes ({last_error}) — continuing",
                                agent_id,
                            )
                            if dead_batches >= 2:
                                # Two batches (four calls) in a row failed — the
                                # provider is down, not unlucky. Stop burning
                                # calls; whatever is designed so far proceeds.
                                yield _event(
                                    PipelineEventType.LOG,
                                    f"[{label}] two consecutive batches failed — "
                                    f"stopping batch generation ({last_error})",
                                    agent_id,
                                )
                                break
                    if not doc.scenes:
                        doc = None
                else:
                    prompt = (
                        f"{_brief_block(user_prompt)}"
                        f"Design the explainer scenes for this document.\n"
                        f"Title: {title}\nAudience: {AudienceLevel(audience).value}\n"
                        f"Language: {language}{figures_block}{research_block}"
                        f"{_plan_block(plan)}\n\n"
                        f"Document text:\n{paper_text}"
                    )
                    for attempt in range(2):
                        try:
                            doc = await _design(prompt)
                        except Exception as exc:  # noqa: BLE001 - provider hiccup → retry once
                            last_error = f"model call failed: {exc}"
                            log.warning("designer attempt %d failed: %s", attempt + 1, exc)
                            continue
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
                scenes_payload = _dump_scenes(doc, figure_map)
                yield _event(
                    PipelineEventType.LOG,
                    f"[{label}] produced {len(scenes_payload)} scenes",
                    agent_id,
                )

                # Agentic length fit — HERE, before verification, so every scene
                # the designer adds/trims still goes through the fact verifier
                # and the visual review. The designer fixes length itself
                # (adding grounded scenes / merging), never a mechanical rescale.
                target_ms = max(1, target_min) * 60_000
                for fit_round in range(1, length_fit_rounds + 1):
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
                        "too SHORT — add new scenes covering more of the document "
                        "(each grounded with citations), or deepen existing ones"
                        if total_ms < target_ms
                        else "too LONG — merge or drop the least important scenes"
                    )
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] cut is {total_ms / 1000:.0f}s vs {target_ms / 1000:.0f}s "
                        f"target ({direction.split(' — ')[0]}) — asking for a fix "
                        f"(round {fit_round}/{length_fit_rounds})",
                        agent_id,
                    )
                    too_short = total_ms < target_ms
                    if too_short:
                        # Ask ONLY for the additional scenes — re-emitting the
                        # whole (large) list risks blowing the output-token cap
                        # and truncating the JSON.
                        missing_ms = target_ms - total_ms
                        summary = "\n".join(
                            f"{i}: {(s.narration or '')[:60]}" for i, s in enumerate(doc.scenes)
                        )
                        fit_prompt = (
                            f"{_brief_block(user_prompt)}"
                            f"Your cut totals {total_ms} ms but the video must total about "
                            f"{target_ms} ms. Design NEW scenes covering more of the document "
                            f"(~{missing_ms} ms more, each grounded with citations) to slot "
                            f"between the existing scenes and the closer. Return ONLY the new "
                            f'scenes as {{"scenes": [...]}} — do NOT repeat existing scenes.'
                            f"\n\nExisting scenes (index: narration):\n{summary}\n\n"
                            f"Document text:\n{paper_text}"
                        )
                    else:
                        fit_prompt = (
                            f"{_brief_block(user_prompt)}"
                            f"Your scene list totals {total_ms} ms but the video must total "
                            f"about {target_ms} ms. It is {direction}. Keep every existing "
                            f"scene's content intact where possible and return the FULL "
                            f"revised scene list.\n\nCurrent scenes:\n{_scenes_json(doc)}\n\n"
                            f"Document text:\n{paper_text}"
                        )
                    try:
                        fixed = await _design(fit_prompt)
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
                    if too_short:
                        # Insert the new scenes before the closer.
                        if len(doc.scenes) > 1:
                            doc.scenes = doc.scenes[:-1] + fixed.scenes + doc.scenes[-1:]
                        else:
                            doc.scenes = doc.scenes + fixed.scenes
                    else:
                        doc = fixed
                    scenes_payload = _dump_scenes(doc, figure_map)
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] adjusted → {len(doc.scenes)} scenes, "
                        f"{sum(s.duration_ms for s in doc.scenes) / 1000:.0f}s",
                        agent_id,
                    )

                # Escalation: length-fit rounds can only pad the existing plan.
                # A cut still far short of target means the PLAN is too thin —
                # go back to the planner for new beats, then design only those
                # (one pass, so a stubborn shortfall can't loop forever).
                total_ms = sum(s.duration_ms for s in doc.scenes)
                if total_ms < target_ms * 0.7:
                    missing_ms = target_ms - total_ms
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] cut is still {total_ms / 1000:.0f}s vs "
                        f"{target_ms / 1000:.0f}s — sending back to the planner "
                        f"for the missing {missing_ms / 1000:.0f}s…",
                        agent_id,
                    )
                    summary = "\n".join(
                        f"{i}: {(s.narration or '')[:60]}" for i, s in enumerate(doc.scenes)
                    )
                    n_new = max(2, missing_ms // 8000)
                    extra: StoryPlan | None = None
                    try:
                        pres = await planner.arun(
                            input=(
                                f"{_brief_block(user_prompt)}"
                                f"The current cut covers only {total_ms} ms of a "
                                f"{target_ms} ms video. Plan about {n_new} NEW beats "
                                f"(4000–9000 ms each, ~{missing_ms} ms total) covering "
                                f"document material the existing scenes skip. Return "
                                f"ONLY the new beats — do not repeat existing ones.\n\n"
                                f"Existing scenes (index: narration):\n{summary}\n\n"
                                f"Document text:\n{paper_text}"
                            ),
                            stream=False,
                        )
                        extra = _coerce_plan(pres.content if pres else None)
                    except Exception as exc:  # noqa: BLE001 - keep the cut
                        log.warning("length re-plan failed: %s", exc)
                    added: GenDocument | None = None
                    if extra is not None:
                        # Same truncation guard as the initial pass: design the
                        # new beats a batch at a time.
                        new_scenes: list[GenScene] = []
                        for bstart in range(0, len(extra.beats), _SCENE_BATCH):
                            bchunk = extra.beats[bstart : bstart + _SCENE_BATCH]
                            beat_lines = "\n".join(
                                f"- {b.headline} — {b.summary} (~{b.duration_ms} ms)"
                                for b in bchunk
                            )
                            try:
                                part = await _design(
                                    f"{_brief_block(user_prompt)}"
                                    f"Design scenes for ONLY these new beats (they slot "
                                    f"between your existing scenes and the closer). "
                                    f'Return ONLY the new scenes as {{"scenes": [...]}} '
                                    f"— do NOT repeat existing scenes.\n\n"
                                    f"New beats:\n{beat_lines}\n\n"
                                    f"Document text:\n{paper_text}"
                                )
                            except Exception as exc:  # noqa: BLE001 - keep the cut
                                log.warning("length re-plan design failed: %s", exc)
                                continue
                            if part is not None and part.scenes:
                                new_scenes.extend(part.scenes)
                        if new_scenes:
                            added = GenDocument(scenes=new_scenes)
                    if added is not None and added.scenes:
                        for sc in added.scenes:
                            sc.index = None  # brand-new scenes — splice, don't patch
                        if len(doc.scenes) > 1:
                            doc.scenes = doc.scenes[:-1] + added.scenes + doc.scenes[-1:]
                        else:
                            doc.scenes = doc.scenes + added.scenes
                        scenes_payload = _dump_scenes(doc, figure_map)
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] re-plan added {len(added.scenes)} scenes → "
                            f"{len(doc.scenes)} total, "
                            f"{sum(s.duration_ms for s in doc.scenes) / 1000:.0f}s",
                            agent_id,
                        )
                    else:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] re-plan produced no usable scenes — keeping cut",
                            agent_id,
                        )

            if agent_id is AgentId.VERIFIER and doc is not None:
                # Agentic verify → revise loop: the verifier grounds every claim
                # in the paper; on failure the designer revises and the verifier
                # re-checks, up to the configured number of rounds. When the
                # rounds run out with fails standing, escalate to the planner:
                # replacement beats → full scene redesigns → one extra re-check
                # (hence the +2 range; the last iteration only re-checks).
                for round_no in range(1, verifier_rounds + 2):
                    report: VerifierReport | None = None
                    try:
                        vres = await verifier.arun(
                            input=(
                                f"Verify these scenes against the document.\n\n"
                                f"Scenes:\n{_scenes_json(doc)}\n\nDocument text:\n{paper_text}"
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
                    if round_no > verifier_rounds:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] re-planned scenes re-checked — proceeding with "
                            f"{len(fails)} unresolved flag(s)",
                            agent_id,
                        )
                        break
                    fail_lines = "\n".join(
                        f"- {f.claim} ({f.source_span}): {f.note or f.level}"
                        for f in report.flags
                        if f.level != "pass"
                    )
                    if round_no == verifier_rounds:
                        # Escalation: revision rounds couldn't ground these
                        # claims — the scenes themselves are bad. The planner
                        # writes replacement beats; the designer rebuilds those
                        # scenes from scratch (new narration AND a new visual —
                        # the redesigned render then goes through the visual
                        # screenshot review below like any other scene).
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] revision rounds exhausted with {len(fails)} "
                            f"fail(s) — sending the failing scenes back to the planner…",
                            agent_id,
                        )
                        summary = "\n".join(
                            f"{i}: {(s.narration or '')[:60]}" for i, s in enumerate(doc.scenes)
                        )
                        rplan: StoryPlan | None = None
                        try:
                            pres = await planner.arun(
                                input=(
                                    f"{_brief_block(user_prompt)}"
                                    "These claims in the current cut failed fact "
                                    f"verification:\n{fail_lines}\n\n"
                                    f"Scenes (index: narration):\n{summary}\n\n"
                                    "Write a replacement beat for EACH scene carrying a "
                                    "failed claim, grounded ONLY in the document. Each "
                                    'beat must carry the 0-based "index" of the scene it '
                                    f"replaces.\n\nDocument text:\n{paper_text}"
                                ),
                                stream=False,
                            )
                            rplan = _coerce_plan(pres.content if pres else None)
                        except Exception as exc:  # noqa: BLE001 - keep the cut
                            log.warning("verifier re-plan failed: %s", exc)
                        beats = [
                            b
                            for b in (rplan.beats if rplan is not None else [])
                            if b.index is not None and 0 <= b.index < len(doc.scenes)
                        ]
                        if not beats:
                            yield _event(
                                PipelineEventType.LOG,
                                f"[{label}] re-plan produced no replacement beats — "
                                f"proceeding with {len(fails)} unresolved flag(s)",
                                agent_id,
                            )
                            break
                        beat_lines = "\n".join(
                            f"- index {b.index}: {b.headline} — {b.summary} (~{b.duration_ms} ms)"
                            for b in beats
                        )
                        revision_prompt = (
                            f"{_brief_block(user_prompt)}"
                            "REDESIGN these scenes from scratch per the new beats — "
                            "new narration AND a new html/css visual, every claim "
                            "grounded in the document. Return ONLY the redesigned "
                            'scenes, each carrying its 0-based "index".\n\n'
                            f"New beats:\n{beat_lines}\n\nDocument text:\n{paper_text}"
                        )
                    else:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] sending scenes back to the designer for revision…",
                            agent_id,
                        )
                        revision_prompt = (
                            f"{_brief_block(user_prompt)}"
                            f"Revise your scenes. The verifier rejected them.\n\n"
                            f"Verifier notes:\n{report.revision_notes}\n\n"
                            f"Flagged claims:\n{fail_lines}\n\n"
                            f"Current scenes:\n{_scenes_json(doc)}\n\n"
                            f"Fix ONLY what the verifier flagged (keep everything else), "
                            f"grounding every claim in the document. If a flagged scene "
                            f"is wrong at its core (not a wording slip), REDESIGN it — "
                            f"new narration AND a new html/css visual. Return ONLY the "
                            f'scenes you changed, each carrying its 0-based "index".'
                            f"\n\nDocument text:\n{paper_text}"
                        )
                    try:
                        revised = await _design(revision_prompt)
                    except Exception as exc:  # noqa: BLE001 - keep current doc on failure
                        log.warning("designer revision failed: %s", exc)
                        revised = None
                    patched = (
                        _patch_scenes(doc, revised) if revised is not None and revised.scenes else 0
                    )
                    if patched:
                        scenes_payload = _dump_scenes(doc, figure_map)
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] designer revised {patched} scene(s) in place "
                            f"(cut stays {len(doc.scenes)} scenes)",
                            agent_id,
                        )
                    elif round_no == verifier_rounds:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] redesign not applicable — proceeding with "
                            f"{len(fails)} unresolved flag(s)",
                            agent_id,
                        )
                        break
                    else:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] revision produced no applicable scenes — keeping cut",
                            agent_id,
                        )

            if agent_id is AgentId.NARRATOR:
                yield _event(
                    PipelineEventType.LOG,
                    f"[{label}] "
                    + (
                        "narration audio will be synthesized once the cut is final (assembler)"
                        if tts_enabled
                        else "TTS is off for this project — no narration audio"
                    ),
                    agent_id,
                )

            if agent_id is AgentId.VERIFIER and doc is not None:
                # Design review with EYES: the render service screenshots every
                # scene and a vision reviewer judges the actual frames —
                # overlapping/clipped/empty/incomplete scenes go back to the
                # designer with concrete CSS fixes. The loop runs until the
                # reviewer approves or two consecutive rounds fix nothing
                # (stall), with a hard cost cap.
                prev_majors: int | None = None
                stalled = 0
                vround = 0
                while vround < visual_max_rounds:
                    vround += 1
                    scenes_payload = _dump_scenes(doc, figure_map)
                    try:
                        images = await _review_images(
                            _screenshot_doc(project_id, title, aspect, scenes_payload)
                        )
                    except Exception as exc:  # noqa: BLE001 - degrade, don't block
                        log.warning("scene screenshots unavailable: %s", exc)
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] visual review skipped (screenshots unavailable)",
                            agent_id,
                        )
                        break
                    if not images:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] visual review skipped (no screenshots)",
                            agent_id,
                        )
                        break
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] visual round {vround}: reviewing {len(images)} "
                        f"scene screenshot(s)…",
                        agent_id,
                    )
                    dreport: DesignReviewReport | None = None
                    try:
                        scene_lines = "\n".join(
                            f"{i}: {s.get('visualType')} — {(s.get('narration') or '')[:70]}"
                            for i, s in enumerate(scenes_payload)
                        )
                        dres = await design_reviewer.arun(
                            input=(
                                "Review these rendered scene screenshots (images are "
                                "in scene order, 0-based).\n\n"
                                + (
                                    "The user's creative brief (the frames MUST honor "
                                    "its story and style; flag scenes that ignore it):\n"
                                    + user_prompt
                                    + "\n\n"
                                    if user_prompt
                                    else ""
                                )
                                + "Scenes:\n"
                                + scene_lines
                            ),
                            images=images,
                            stream=False,
                        )
                        content = dres.content if dres else None
                        if isinstance(content, DesignReviewReport):
                            dreport = content
                        else:
                            data = _extract_data(content)
                            if isinstance(data, dict):
                                dreport = DesignReviewReport.model_validate(data)
                    except Exception as exc:  # noqa: BLE001 - review is best-effort
                        log.warning("design review round %d failed: %s", vround, exc)
                    if dreport is None:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] visual reviewer unavailable — proceeding",
                            agent_id,
                        )
                        break
                    # Blind round: the reviewer answered without receiving the
                    # screenshots (endpoint dropped the image parts) and flags
                    # every scene with "no visual content". Acting on that
                    # would send the designer phantom fixes — skip the round.
                    blind_markers = (
                        "no visual content",
                        "no screenshot",
                        "missing rendered",
                        "no image",
                    )
                    blind = [
                        i
                        for i in dreport.issues
                        if any(m in i.problem.lower() for m in blind_markers)
                    ]
                    if dreport.issues and len(blind) * 2 >= len(dreport.issues):
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] visual round {vround}: reviewer did not receive "
                            f"the screenshots — skipping this round",
                            agent_id,
                        )
                        break
                    majors = [i for i in dreport.issues if i.severity == "major"]
                    for issue in dreport.issues:
                        payload = {
                            "id": new_id("vf"),
                            "claim": f"scene {issue.scene_index}: {issue.problem}",
                            "sourceSpan": f"scene {issue.scene_index} (visual)",
                            "level": "fail" if issue.severity == "major" else "warn",
                            "note": issue.fix,
                        }
                        yield _event(PipelineEventType.FLAG, payload, agent_id)
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] visual round {vround}: {len(dreport.issues)} issue(s), "
                        f"{len(majors)} major",
                        agent_id,
                    )
                    if dreport.approved and not majors:
                        yield _event(
                            PipelineEventType.LOG, f"[{label}] visual design approved", agent_id
                        )
                        break
                    # Stall detection: a round "made progress" only if it
                    # resolved at least one major issue vs the previous round.
                    if prev_majors is not None and len(majors) >= prev_majors:
                        stalled += 1
                    else:
                        stalled = 0
                    prev_majors = len(majors)
                    if stalled >= visual_stall_rounds:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] two review rounds with no progress — proceeding "
                            f"with {len(majors)} unresolved issue(s)",
                            agent_id,
                        )
                        break
                    if vround >= visual_max_rounds:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] review round cap reached — proceeding with "
                            f"{len(majors)} unresolved issue(s)",
                            agent_id,
                        )
                        break
                    issue_lines = "\n".join(
                        f"- scene {i.scene_index} [{i.severity}]: {i.problem} → FIX: {i.fix}"
                        for i in dreport.issues
                    )
                    visual_prompt = (
                        f"{_brief_block(user_prompt)}"
                        "The art director reviewed SCREENSHOTS of your rendered scenes "
                        "and rejected the cut. Fix EXACTLY the flagged scenes' html/css "
                        "(layout, overlap, sizing, backgrounds). Remember: full-frame "
                        "themed backgrounds, no overlapping text/images, complete "
                        "visual compositions.\n\n"
                        f"Issues:\n{issue_lines}\n\n"
                        f"Current scenes:\n{_scenes_json(doc)}\n\n"
                        "Return ONLY the fixed scenes, each carrying its 0-based "
                        '"index" from the issue list — do NOT resend unchanged scenes.'
                    )
                    try:
                        revised = await _design(visual_prompt)
                    except Exception as exc:  # noqa: BLE001 - keep current doc
                        log.warning("visual revision failed: %s", exc)
                        revised = None
                    patched = (
                        _patch_scenes(doc, revised) if revised is not None and revised.scenes else 0
                    )
                    if patched:
                        scenes_payload = _dump_scenes(doc, figure_map)
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] designer fixed {patched} scene(s) in place "
                            f"(cut stays {len(doc.scenes)} scenes)",
                            agent_id,
                        )
                    else:
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] visual revision not applicable — keeping cut",
                            agent_id,
                        )
                        break

            if agent_id is AgentId.ASSEMBLER and doc is not None:
                # Length was fitted at the designer stage (so added scenes went
                # through verification); here we just report the final cut.
                total_ms = sum(s.duration_ms for s in doc.scenes)
                yield _event(
                    PipelineEventType.LOG,
                    f"[{label}] final cut: {len(doc.scenes)} scenes, "
                    f"{total_ms / 1000:.0f}s (target {target_min} min)",
                    agent_id,
                )

                # Narration audio (TTS) — synthesized against the FINAL cut so
                # revisions can't orphan clips. Scene durations stretch to fit
                # their narration; clips land on params.audioUrl, which the
                # compiler turns into <audio class="clip"> elements.
                if tts_enabled:
                    try:
                        from vyakhya.services.tts import narrate_scene, resolve_tts_connection

                        async with sm() as session:
                            tts = await resolve_tts_connection(session)
                        if tts is None:
                            yield _event(
                                PipelineEventType.LOG,
                                f"[{label}] TTS is on but no TTS connection is configured "
                                "— add one in Model Config; skipping narration audio",
                                agent_id,
                            )
                        else:
                            tconn, tkey = tts
                            todo = [
                                (i, s, (s.narration or "").strip())
                                for i, s in enumerate(doc.scenes)
                                if (s.narration or "").strip()
                            ]
                            yield _event(
                                PipelineEventType.LOG,
                                f"[{label}] synthesizing narration for {len(todo)} "
                                f"scene(s) via {tconn.provider} ({tconn.model})…",
                                agent_id,
                            )
                            import asyncio as _asyncio

                            sem = _asyncio.Semaphore(4)

                            async def _voice(  # noqa: ANN202
                                i: int, text: str, _sem=sem, _c=tconn, _k=tkey
                            ):
                                async with _sem:
                                    return await narrate_scene(project_id, i, text, _c, _k)

                            results = await _asyncio.gather(
                                *(_voice(i, text) for i, _, text in todo),
                                return_exceptions=True,
                            )
                            voiced = 0
                            for (i, s, _), res in zip(todo, results, strict=True):
                                if isinstance(res, BaseException):
                                    log.warning("TTS failed for scene %d: %s", i, res)
                                    continue
                                url, ms = res
                                s.params.audio_url = url
                                s.params.audio_duration_ms = ms
                                if ms and s.duration_ms < ms + 300:
                                    s.duration_ms = min(ms + 500, 60_000)
                                voiced += 1
                            scenes_payload = _dump_scenes(doc, figure_map)
                            yield _event(
                                PipelineEventType.LOG,
                                f"[{label}] narration audio attached to {voiced}/"
                                f"{len(todo)} scene(s)",
                                agent_id,
                            )
                    except Exception as exc:  # noqa: BLE001 - audio is an enhancement
                        log.warning("narration synthesis failed: %s", exc)
                        yield _event(
                            PipelineEventType.LOG,
                            f"[{label}] narration synthesis skipped: {exc}",
                            agent_id,
                        )

            yield _event(PipelineEventType.STATUS, AgentStatus.DONE.value, agent_id)
            yield _event(PipelineEventType.PROGRESS, round((idx + 1) / total, 3))

            if agent_id is AgentId.ASSEMBLER and scenes_payload:
                yield _event(PipelineEventType.SCENES, scenes_payload, agent_id)

        yield _event(PipelineEventType.DONE, None)
