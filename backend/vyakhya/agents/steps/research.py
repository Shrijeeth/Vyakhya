"""Comprehension step: best-effort web research (search + Wikipedia) for
grounding context the document itself doesn't carry."""

from __future__ import annotations

from vyakhya.agents.context import PipelineContext
from vyakhya.agents.schemas import ResearchNotes, coerce_model
from vyakhya.core.logging import get_logger
from vyakhya.enums import AgentId

log = get_logger(__name__)


async def run(ctx: PipelineContext) -> None:
    async with ctx.stage(AgentId.COMPREHENSION, "Comprehension"):
        if not ctx.agents.researcher.tools:
            return
        try:
            content = await ctx.call(
                ctx.agents.researcher,
                f"Research context for explaining this document.\n"
                f"Title: {ctx.title}\n\nOpening of the document:\n{ctx.paper_text[:3000]}",
                heartbeat=(AgentId.COMPREHENSION, "Comprehension"),
                attempts=1,
            )
            ctx.research = coerce_model(content, ResearchNotes)  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001 - research is best-effort
            log.warning("web research failed: %s", exc)
            ctx.log(AgentId.COMPREHENSION, f"[Comprehension] web research skipped: {exc}")
            return
        if ctx.research is not None:
            ctx.log(
                AgentId.COMPREHENSION,
                f"[Comprehension] gathered {len(ctx.research.key_points)} research "
                f"note(s) from the web",
            )
