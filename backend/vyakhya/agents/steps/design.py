"""Design step: the designer executes the Scene Creator's outline, a batch
of scenes per call (the full cut's JSON cannot fit one completion). It gets
the descriptions and the HyperFrames skills — not the document; the outline
already carries the content."""

from __future__ import annotations

from vyakhya.agents.context import SCENE_BATCH, PipelineContext
from vyakhya.agents.schemas import GenDocument, coerce_document, dump_scenes
from vyakhya.core.logging import get_logger
from vyakhya.enums import AgentId

log = get_logger(__name__)

_HB = (AgentId.VISUAL_DESIGNER, "Visual Designer")


def figures_block(ctx: PipelineContext) -> str:
    if not ctx.figures:
        return ""
    lines = "\n".join(
        f"- {f['id']}: page {f['page']}, {f['width']}x{f['height']}px" for f in ctx.figures
    )
    return f"\n\nFigures cropped from the document (embed via figureId):\n{lines}"


async def design(ctx: PipelineContext, prompt: str) -> GenDocument | None:
    return coerce_document(await ctx.call(ctx.agents.designer, prompt, heartbeat=_HB))


def build_prompt(ctx: PipelineContext, specs: list[tuple[int, str]], theme_tail: str = "") -> str:
    """Prompt to build the given (index, description) scenes exactly."""
    described = "\n\n".join(f"### Scene {i + 1}\n{spec}" for i, spec in specs)
    return (
        f"{ctx.brief}"
        f"Build these scene descriptions as HyperFrames frames — one scene per "
        f"description, in order, implementing each Visual and Animation section "
        f'fully. Return EXACTLY {len(specs)} scenes as {{"scenes": [...]}}.'
        f"{theme_tail}{figures_block(ctx)}\n\n{described}"
    )


async def run(ctx: PipelineContext) -> None:
    async with ctx.stage(AgentId.VISUAL_DESIGNER, "Visual Designer"):
        outline = ctx.outline
        doc = GenDocument(scenes=[])
        n_batches = (len(outline) + SCENE_BATCH - 1) // SCENE_BATCH
        dead = 0
        for start in range(0, len(outline), SCENE_BATCH):
            chunk = list(enumerate(outline))[start : start + SCENE_BATCH]
            batch_no = start // SCENE_BATCH + 1
            ctx.log(
                AgentId.VISUAL_DESIGNER,
                f"[Visual Designer] building scenes {start + 1}–{start + len(chunk)} "
                f"of {len(outline)} (batch {batch_no}/{n_batches})…",
            )
            theme_tail = ""
            if doc.scenes:
                theme_tail = (
                    " Keep the SAME visual theme (background, palette, typography) "
                    "as the scenes already built."
                )
            try:
                batch = await design(ctx, build_prompt(ctx, chunk, theme_tail))
            except Exception as exc:  # noqa: BLE001 - a dead batch leaves a gap
                log.warning("design batch %d failed: %s", batch_no, exc)
                batch = None
            if batch is not None and batch.scenes:
                dead = 0
                for sc in batch.scenes:
                    sc.index = None  # appended, never patched
                doc.scenes.extend(batch.scenes)
                ctx.log(
                    AgentId.VISUAL_DESIGNER,
                    f"[Visual Designer] batch {batch_no}/{n_batches} → "
                    f"{len(batch.scenes)} scene(s), {len(doc.scenes)} total",
                )
            else:
                dead += 1
                ctx.log(
                    AgentId.VISUAL_DESIGNER,
                    f"[Visual Designer] batch {batch_no}/{n_batches} produced no "
                    f"valid scenes — continuing",
                )
                if dead >= 2:
                    ctx.log(
                        AgentId.VISUAL_DESIGNER,
                        "[Visual Designer] two consecutive batches failed — stopping",
                    )
                    break
        if not doc.scenes:
            ctx.log(AgentId.VISUAL_DESIGNER, "[Visual Designer] produced no valid scenes")
            raise RuntimeError("visual designer produced no scenes")
        ctx.doc = doc
        total_ms = sum(s.duration_ms for s in doc.scenes)
        ctx.log(
            AgentId.VISUAL_DESIGNER,
            f"[Visual Designer] built {len(doc.scenes)} scenes, {total_ms / 1000:.0f}s "
            f"(target {ctx.target_min} min)",
        )
        ctx.scenes_payload = dump_scenes(ctx.doc, ctx.figure_map)
