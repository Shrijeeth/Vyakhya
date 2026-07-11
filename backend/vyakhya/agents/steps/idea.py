"""Video Idea step: document + user brief → one detailed video idea the
rest of the crew executes. No HyperFrames knowledge here — pure story."""

from __future__ import annotations

from vyakhya.agents.context import PipelineContext
from vyakhya.agents.schemas import VideoIdea, coerce_model
from vyakhya.enums import AgentId, AudienceLevel


async def run(ctx: PipelineContext) -> None:
    async with ctx.stage(AgentId.PLANNER, "Video Idea"):
        content = await ctx.call(
            ctx.agents.idea,
            f"{ctx.brief}"
            f"Create the video idea for this document.\n"
            f"Title: {ctx.title}\nAudience: {AudienceLevel(ctx.audience).value}\n"
            f"Language: {ctx.language}\nTarget length: {ctx.target_min} min\n\n"
            f"Document text:\n{ctx.paper_text}",
            heartbeat=(AgentId.PLANNER, "Video Idea"),
        )
        idea = coerce_model(content, VideoIdea)
        if idea is None or not idea.idea.strip():  # type: ignore[union-attr]
            ctx.log(AgentId.PLANNER, "[Video Idea] no usable idea produced")
            raise RuntimeError("video idea agent produced no idea")
        ctx.idea = idea.idea.strip()  # type: ignore[union-attr]
        ctx.log(
            AgentId.PLANNER,
            f"[Video Idea] idea ready ({len(ctx.idea)} chars): {ctx.idea.splitlines()[0][:100]}",
        )
