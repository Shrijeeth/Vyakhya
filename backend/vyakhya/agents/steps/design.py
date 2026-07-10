"""Design step: the designer writes the whole video, a batch of scenes per
call (the full cut's JSON cannot fit one completion), then tops up length.

No separate planner — the scene budget is computed from the target length
and the designer carries the story across batches via the running tail of
scenes it already wrote."""

from __future__ import annotations

from vyakhya.agents.context import DURATION_TOLERANCE, SCENE_BATCH, PipelineContext
from vyakhya.agents.schemas import GenDocument, coerce_document, dump_scenes
from vyakhya.core.logging import get_logger
from vyakhya.enums import AgentId, AudienceLevel

log = get_logger(__name__)

_HB = (AgentId.VISUAL_DESIGNER, "Visual Designer")
_AVG_SCENE_MS = 6000


def scene_budget(target_ms: int) -> int:
    return max(3, min(60, round(target_ms / _AVG_SCENE_MS)))


def _figures_block(ctx: PipelineContext) -> str:
    if not ctx.figures:
        return ""
    lines = "\n".join(
        f"- {f['id']}: page {f['page']}, {f['width']}x{f['height']}px" for f in ctx.figures
    )
    return f"\n\nFigures cropped from the document (embed via figureId):\n{lines}"


async def _design(ctx: PipelineContext, prompt: str) -> GenDocument | None:
    return coerce_document(await ctx.call(ctx.agents.designer, prompt, heartbeat=_HB))


async def _design_batches(ctx: PipelineContext, total: int) -> GenDocument:
    """Write scenes 1..total in SCENE_BATCH chunks, carrying the story tail
    between calls; two consecutive dead batches stop generation."""
    doc = GenDocument(scenes=[])
    n_batches = (total + SCENE_BATCH - 1) // SCENE_BATCH
    dead = 0
    for start in range(0, total, SCENE_BATCH):
        count = min(SCENE_BATCH, total - start)
        batch_no = start // SCENE_BATCH + 1
        ctx.log(
            AgentId.VISUAL_DESIGNER,
            f"[Visual Designer] writing scenes {start + 1}–{start + count} of {total} "
            f"(batch {batch_no}/{n_batches})…",
        )
        position = (
            "This is the OPENING of the video — start with a hook."
            if start == 0
            else "This is the ENDING of the video — land the payoff and close."
            if start + count >= total
            else "This is the middle of the video — keep the story building."
        )
        continuity = ""
        if doc.scenes:
            tail = "\n".join(f"- {(s.narration or '')[:70]}" for s in doc.scenes[-3:])
            continuity = (
                f"\nThe story so far ends with:\n{tail}\nContinue it seamlessly and "
                "keep the SAME visual theme (background, palette, typography)."
            )
        prompt = (
            f"{ctx.brief}"
            f"Write scenes {start + 1}–{start + count} of a {total}-scene explainer "
            f"video about this document. {position}{continuity}\n"
            f'Return EXACTLY {count} scenes as {{"scenes": [...]}}.\n'
            f"Title: {ctx.title}\nAudience: {AudienceLevel(ctx.audience).value}\n"
            f"Language: {ctx.language}{_figures_block(ctx)}\n\n"
            f"Document text:\n{ctx.paper_text}"
        )
        try:
            batch = await _design(ctx, prompt)
        except Exception as exc:  # noqa: BLE001 - a dead batch leaves a shortfall
            log.warning("batch %d failed: %s", batch_no, exc)
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
                f"[Visual Designer] batch {batch_no}/{n_batches} produced no valid "
                f"scenes — continuing",
            )
            if dead >= 2:
                ctx.log(
                    AgentId.VISUAL_DESIGNER,
                    "[Visual Designer] two consecutive batches failed — stopping",
                )
                break
    return doc


async def _fit_length(ctx: PipelineContext) -> None:
    """Simple top-up/trim loop until the cut is within tolerance."""
    doc = ctx.doc
    assert doc is not None
    for fit_round in range(1, ctx.tunables.length_fit_rounds + 1):
        total_ms = sum(s.duration_ms for s in doc.scenes)
        if abs(total_ms - ctx.target_ms) / ctx.target_ms <= DURATION_TOLERANCE:
            ctx.log(
                AgentId.VISUAL_DESIGNER,
                f"[Visual Designer] cut is {total_ms / 1000:.0f}s — within tolerance "
                f"of the {ctx.target_min} min target",
            )
            return
        too_short = total_ms < ctx.target_ms
        ctx.log(
            AgentId.VISUAL_DESIGNER,
            f"[Visual Designer] cut is {total_ms / 1000:.0f}s vs "
            f"{ctx.target_ms / 1000:.0f}s ({'too SHORT' if too_short else 'too LONG'}) "
            f"— fixing (round {fit_round}/{ctx.tunables.length_fit_rounds})",
        )
        if too_short:
            summary = "\n".join(
                f"{i}: {(s.narration or '')[:60]}" for i, s in enumerate(doc.scenes)
            )
            prompt = (
                f"{ctx.brief}"
                f"Your cut totals {total_ms} ms; the video must total about "
                f"{ctx.target_ms} ms. Write NEW scenes (~{ctx.target_ms - total_ms} ms "
                f"more, grounded in the document) that deepen the story before its "
                f'closer. Return ONLY the new scenes as {{"scenes": [...]}}.\n\n'
                f"Existing scenes (index: narration):\n{summary}\n\n"
                f"Document text:\n{ctx.paper_text}"
            )
        else:
            from vyakhya.agents.schemas import scenes_json

            prompt = (
                f"{ctx.brief}"
                f"Your scene list totals {total_ms} ms; the video must total about "
                f"{ctx.target_ms} ms — too LONG. Merge or drop the least important "
                f"scenes and return the FULL revised list.\n\n"
                f"Current scenes:\n{scenes_json(doc)}\n\nDocument text:\n{ctx.paper_text}"
            )
        try:
            fixed = await _design(ctx, prompt)
        except Exception as exc:  # noqa: BLE001 - keep the cut
            log.warning("length-fit round %d failed: %s", fit_round, exc)
            fixed = None
        if fixed is None or not fixed.scenes:
            ctx.log(
                AgentId.VISUAL_DESIGNER,
                "[Visual Designer] length fix produced no valid scenes — keeping cut",
            )
            return
        if too_short:
            for sc in fixed.scenes:
                sc.index = None
            if len(doc.scenes) > 1:
                doc.scenes = doc.scenes[:-1] + fixed.scenes + doc.scenes[-1:]
            else:
                doc.scenes = doc.scenes + fixed.scenes
        else:
            ctx.doc = doc = fixed
        ctx.log(
            AgentId.VISUAL_DESIGNER,
            f"[Visual Designer] adjusted → {len(doc.scenes)} scenes, "
            f"{sum(s.duration_ms for s in doc.scenes) / 1000:.0f}s",
        )


async def run(ctx: PipelineContext) -> None:
    # Pass-through stages the UI sequence expects; their work now lives in
    # the designer itself.
    async with ctx.stage(AgentId.COMPREHENSION, "Comprehension"):
        ctx.log(AgentId.COMPREHENSION, "[Comprehension] document text loaded for the designer")
    async with ctx.stage(AgentId.PLANNER, "Planner"):
        n = scene_budget(ctx.target_ms)
        ctx.log(
            AgentId.PLANNER,
            f"[Planner] scene budget: {n} scenes for the {ctx.target_min} min target",
        )
    async with ctx.stage(AgentId.SCRIPTWRITER, "Scriptwriter"):
        ctx.log(
            AgentId.SCRIPTWRITER,
            "[Scriptwriter] narration is written per scene by the designer",
        )

    async with ctx.stage(AgentId.VISUAL_DESIGNER, "Visual Designer"):
        ctx.doc = await _design_batches(ctx, scene_budget(ctx.target_ms))
        if not ctx.doc.scenes:
            ctx.log(AgentId.VISUAL_DESIGNER, "[Visual Designer] produced no valid scenes")
            raise RuntimeError("visual designer produced no scenes")
        ctx.log(
            AgentId.VISUAL_DESIGNER,
            f"[Visual Designer] produced {len(ctx.doc.scenes)} scenes",
        )
        await _fit_length(ctx)
        ctx.scenes_payload = dump_scenes(ctx.doc, ctx.figure_map)
