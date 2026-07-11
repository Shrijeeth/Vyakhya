"""Scene Creator step: the video, ONE SCENE AT A TIME.

Each call sees the overall video idea, the previous scene's description,
and the scene's position (the first scene is the opening screen, the last
is the ending/credits screen). The result is the ordered outline — one
markdown description per scene — the designer then executes."""

from __future__ import annotations

from vyakhya.agents.context import PipelineContext
from vyakhya.agents.schemas import SceneSpec, coerce_model
from vyakhya.core.logging import get_logger
from vyakhya.enums import AgentId

log = get_logger(__name__)

_HB = (AgentId.SCRIPTWRITER, "Scene Creator")
_AVG_SCENE_MS = 6000


def scene_budget(target_ms: int) -> int:
    return max(3, min(60, round(target_ms / _AVG_SCENE_MS)))


def _position_note(i: int, total: int) -> str:
    if i == 0:
        return "This is scene 1 — the OPENING screen: hook the audience immediately."
    if i == total - 1:
        return (
            f"This is scene {total} of {total} — the ENDING screen: land the "
            "payoff and close (takeaway/credits)."
        )
    return f"This is scene {i + 1} of {total} — continue the story seamlessly."


async def create_scene(
    ctx: PipelineContext, i: int, total: int, prev: str | None, note: str = ""
) -> str | None:
    """One Scene Creator call → one markdown scene description."""
    prev_block = f"\n\nThe previous scene was:\n{prev}" if prev else ""
    content = await ctx.call(
        ctx.agents.scene_creator,
        f"{ctx.brief}"
        f"{_position_note(i, total)}{note}\n\n"
        f"The overall video idea:\n{ctx.idea}{prev_block}",
        heartbeat=_HB,
    )
    spec = coerce_model(content, SceneSpec)
    text = (spec.scene if spec is not None else "").strip()  # type: ignore[union-attr]
    return text or None


async def run(ctx: PipelineContext) -> None:
    async with ctx.stage(AgentId.SCRIPTWRITER, "Scene Creator"):
        total = scene_budget(ctx.target_ms)
        ctx.log(
            AgentId.SCRIPTWRITER,
            f"[Scene Creator] outlining {total} scenes for the {ctx.target_min} min target…",
        )
        outline: list[str] = []
        misses = 0
        for i in range(total):
            try:
                scene = await create_scene(ctx, i, total, outline[-1] if outline else None)
            except Exception as exc:  # noqa: BLE001 - a missed scene leaves a gap
                log.warning("scene %d failed: %s", i, exc)
                scene = None
            if scene is None:
                misses += 1
                ctx.log(
                    AgentId.SCRIPTWRITER,
                    f"[Scene Creator] scene {i + 1}/{total} produced nothing — skipping",
                )
                if misses >= 3:
                    ctx.log(
                        AgentId.SCRIPTWRITER,
                        "[Scene Creator] three misses — stopping the outline here",
                    )
                    break
                continue
            misses = 0
            outline.append(scene)
            if (i + 1) % 5 == 0 or i + 1 == total:
                ctx.log(
                    AgentId.SCRIPTWRITER,
                    f"[Scene Creator] {len(outline)}/{total} scenes outlined",
                )
        if not outline:
            ctx.log(AgentId.SCRIPTWRITER, "[Scene Creator] produced no scenes")
            raise RuntimeError("scene creator produced no scenes")
        ctx.outline = outline
        ctx.log(AgentId.SCRIPTWRITER, f"[Scene Creator] outline complete: {len(outline)} scenes")
