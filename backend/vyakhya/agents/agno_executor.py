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
from typing import Any

from pydantic import BaseModel, Field
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

log = get_logger(__name__)


# ── Generation schema (no ids/index — the persistence layer assigns those) ────
class GenCitation(BaseModel):
    label: str
    source_span: str = Field(serialization_alias="sourceSpan")


class GenScene(BaseModel):
    narration: str
    visual_type: VisualType = Field(serialization_alias="visualType")
    params: dict[str, Any] = Field(default_factory=dict)
    caption_style: CaptionStyle = Field(
        default=CaptionStyle.MINIMAL, serialization_alias="captionStyle"
    )
    transition: SceneTransition = SceneTransition.FADE
    duration_ms: int = Field(default=6000, serialization_alias="durationMs")
    citations: list[GenCitation] = Field(default_factory=list)


class GenDocument(BaseModel):
    scenes: list[GenScene]


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
    "Every scene needs at least one citation grounding it to a source span in the "
    "paper (e.g. '§3.2, p. 4').",
]


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
    """Best-effort extract of the paper's text for the agent's context."""
    url = project.paper_file_url
    if not url:
        return f"(No PDF text available. Title: {project.title}.)"
    try:
        import httpx
        from pypdf import PdfReader

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        import io

        reader = PdfReader(io.BytesIO(resp.content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return text[:60_000] or f"(Empty PDF. Title: {project.title}.)"
    except Exception as exc:  # noqa: BLE001 - degrade gracefully to title-only
        log.warning("paper text extraction failed for %s: %s", project.id, exc)
        return f"(Could not read PDF: {exc}. Title: {project.title}.)"


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

        model = build_llm_model(conn.provider, conn.model, api_key, conn.base_url)
        skills = get_hyperframes_skills()
        designer = Agent(
            name="Visual Designer",
            model=model,
            skills=skills,
            instructions=[*_DESIGNER_INSTRUCTIONS, _length_instruction(target_min, tts_enabled)],
            output_schema=GenDocument,
            markdown=False,
        )

        total = len(AGENT_SEQUENCE)
        scenes_payload: list[dict] = []

        for idx, (agent_id, label) in enumerate(AGENT_SEQUENCE):
            yield _event(PipelineEventType.STATUS, AgentStatus.RUNNING.value, agent_id)
            yield _event(PipelineEventType.LOG, f"[{label}] working…", agent_id)

            if agent_id is AgentId.VISUAL_DESIGNER:
                prompt = (
                    f"Design the explainer scenes for this paper.\n"
                    f"Title: {title}\nAudience: {AudienceLevel(audience).value}\n"
                    f"Language: {language}\n\nPaper text:\n{paper_text}"
                )
                result = await designer.arun(input=prompt, stream=False)
                doc: GenDocument | None = result.content if result else None
                if isinstance(doc, GenDocument):
                    scenes_payload = [s.model_dump(by_alias=True) for s in doc.scenes]
                    yield _event(
                        PipelineEventType.LOG,
                        f"[{label}] produced {len(scenes_payload)} scenes",
                        agent_id,
                    )

            yield _event(PipelineEventType.STATUS, AgentStatus.DONE.value, agent_id)
            yield _event(PipelineEventType.PROGRESS, round((idx + 1) / total, 3))

            if agent_id is AgentId.ASSEMBLER and scenes_payload:
                yield _event(PipelineEventType.SCENES, scenes_payload, agent_id)

        yield _event(PipelineEventType.DONE, None)
