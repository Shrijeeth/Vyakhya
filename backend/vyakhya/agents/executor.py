"""The real Agno pipeline executor.

Implements the ``PipelineExecutor`` async-iterator contract (status / log /
flag / scenes / progress / done events): builds the ``PipelineContext`` and
the agent crew from Model Config, runs the Agno Workflow in a task, and
bridges the steps' events out through a queue."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from vyakhya.agents.context import PipelineContext, Tunables
from vyakhya.agents.crew import build_agents
from vyakhya.agents.pipeline import _event
from vyakhya.core.database import get_sessionmaker
from vyakhya.core.logging import get_logger
from vyakhya.db.models.project import Project
from vyakhya.enums import AgentId, PipelineEventType

log = get_logger(__name__)


def _length_note(target_min: int, tts: bool) -> str:
    target_ms = max(1, target_min) * 60_000
    n_lo = max(3, target_ms // 9000)
    n_hi = max(n_lo + 2, target_ms // 4000)
    narration = (
        "Every scene needs narration (what the voice-over says)."
        if tts
        else "Narration is optional (no voice-over); keep any narration terse."
    )
    return (
        f"The video should total about {target_ms} ms ({target_min} min): roughly "
        f"{n_lo}–{n_hi} scenes at 4000–9000 ms each. {narration}"
    )


async def _load_paper_text(project: Project) -> str:
    """Prefer the text extracted at upload; fall back to fetching the PDF."""
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


class AgnoPipelineExecutor:
    """Real Agno workflow. Emits the same events as the simulated executor."""

    async def run(self, project_id: str) -> AsyncIterator[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        ctx = await self._build_context(project_id, queue.put_nowait)
        if ctx is None:
            yield _event(
                PipelineEventType.LOG,
                "No LLM connection configured — add one in Model Config.",
                AgentId.INGESTOR,
            )
            raise RuntimeError("no LLM connection configured for the Agno pipeline")

        from vyakhya.agents.workflow import build_pipeline_workflow

        workflow = build_pipeline_workflow(ctx)
        task = asyncio.create_task(workflow.arun(input=ctx.title))
        while True:
            try:
                yield await asyncio.wait_for(queue.get(), timeout=0.5)
                continue
            except TimeoutError:
                pass
            if task.done() and queue.empty():
                break
        result = task.result()  # re-raises a workflow crash
        status = str(getattr(getattr(result, "status", None), "value", "") or "").lower()
        if status == "error":
            raise RuntimeError(str(getattr(result, "content", None) or "pipeline step failed"))
        yield _event(PipelineEventType.DONE, None)

    async def _build_context(self, project_id: str, emit) -> PipelineContext | None:  # noqa: ANN001
        sm = get_sessionmaker()
        async with sm() as session:
            project = await session.get(Project, project_id)
            if project is None:
                raise RuntimeError(f"project {project_id} not found")
            from vyakhya.services.connections import get_agent_settings

            aset = await get_agent_settings(session)
            target_min = project.target_length_min or 3
            agents = await build_agents(session, _length_note(target_min, project.tts_enabled))
            if agents is None:
                return None
            return PipelineContext(
                project_id=project_id,
                title=project.title,
                audience=project.audience,
                language=project.language,
                target_min=target_min,
                tts_enabled=project.tts_enabled,
                aspect=project.aspect_ratio.value,
                user_prompt=(project.user_prompt or "").strip(),
                paper_text=await _load_paper_text(project),
                figures=list(project.figures or []),
                paper_file_url=project.paper_file_url,
                tunables=Tunables(
                    review_rounds=aset.visual_max_rounds,
                    review_stall_rounds=aset.visual_stall_rounds,
                    length_fit_rounds=aset.length_fit_rounds,
                ),
                agents=agents,
                emit=emit,
            )
