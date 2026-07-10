"""Planner step: beat sheet sized to the target length. The designer builds
one scene per beat, so a thin plan (the main cause of short cuts) is caught
here, not three stages later."""

from __future__ import annotations

from vyakhya.agents.context import PipelineContext
from vyakhya.agents.schemas import StoryPlan, coerce_plan
from vyakhya.core.logging import get_logger
from vyakhya.enums import AgentId, AudienceLevel

log = get_logger(__name__)


def beat_budget(target_ms: int) -> tuple[int, int]:
    """Beat-count range for a target duration (scenes run 4000-9000 ms)."""
    lo = max(3, target_ms // 9000)
    return lo, max(lo + 2, target_ms // 4000)


def plan_block(plan: StoryPlan | None) -> str:
    """The beat sheet as prompt text for the designer."""
    if plan is None or not plan.beats:
        return ""
    lines = "\n".join(
        f"{i}: {b.headline} — {b.summary} (~{b.duration_ms} ms)" for i, b in enumerate(plan.beats)
    )
    return f"\n\nStory plan — design ONE scene per beat, in order:\n{lines}"


async def run(ctx: PipelineContext) -> None:
    async with ctx.stage(AgentId.PLANNER, "Planner"):
        n_lo, n_hi = beat_budget(ctx.target_ms)
        research_note = (
            f"\n\nWeb research summary:\n{ctx.research.summary}"
            if ctx.research is not None and ctx.research.summary
            else ""
        )
        try:
            content = await ctx.call(
                ctx.agents.planner,
                f"{ctx.brief}"
                f"Plan the beat sheet for this explainer video.\n"
                f"Title: {ctx.title}\nAudience: {AudienceLevel(ctx.audience).value}\n"
                f"Target: about {ctx.target_ms} ms total — plan {n_lo}–{n_hi} beats "
                f"of 4000–9000 ms each, summing to the target."
                f"{research_note}\n\nDocument text:\n{ctx.paper_text}",
                heartbeat=(AgentId.PLANNER, "Planner"),
            )
            ctx.plan = coerce_plan(content)
        except Exception as exc:  # noqa: BLE001 - the designer can work planless
            log.warning("planner failed: %s", exc)
        if ctx.plan is not None:
            planned_ms = sum(b.duration_ms for b in ctx.plan.beats)
            ctx.log(
                AgentId.PLANNER,
                f"[Planner] {len(ctx.plan.beats)} beats planned "
                f"(~{planned_ms / 1000:.0f}s vs {ctx.target_ms / 1000:.0f}s target)",
            )
        else:
            ctx.log(
                AgentId.PLANNER,
                "[Planner] no usable plan — the designer will structure the video itself",
            )

    # The designer writes narration scene by scene; the scriptwriter stage
    # exists in the UI sequence, so acknowledge it.
    async with ctx.stage(AgentId.SCRIPTWRITER, "Scriptwriter"):
        ctx.log(
            AgentId.SCRIPTWRITER,
            "[Scriptwriter] narration is written per scene by the visual designer",
        )
