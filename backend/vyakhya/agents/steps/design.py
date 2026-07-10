"""Visual designer step: scenes in beat-sized batches, then length fit.

Batching exists because the full cut's JSON cannot fit one completion —
a 36-beat video is ~50k output tokens and WILL truncate. A cut still far
short after the fit rounds means the PLAN was too thin, so the planner
writes extra beats and the designer renders only those (one pass)."""

from __future__ import annotations

from vyakhya.agents.context import DURATION_TOLERANCE, SCENE_BATCH, PipelineContext
from vyakhya.agents.schemas import GenDocument, coerce_document, coerce_plan, dump_scenes
from vyakhya.agents.steps.plan import plan_block
from vyakhya.core.logging import get_logger
from vyakhya.enums import AgentId, AudienceLevel

log = get_logger(__name__)

_HB = (AgentId.VISUAL_DESIGNER, "Visual Designer")


def _context_blocks(ctx: PipelineContext) -> str:
    figures = ""
    if ctx.figures:
        lines = "\n".join(
            f"- {f['id']}: page {f['page']}, {f['width']}x{f['height']}px" for f in ctx.figures
        )
        figures = f"\n\nFigures cropped from the document (embed via figureId):\n{lines}"
    research = ""
    if ctx.research is not None and (ctx.research.summary or ctx.research.key_points):
        notes = "\n".join(f"- {p}" for p in ctx.research.key_points)
        research = f"\n\nWeb research context:\n{ctx.research.summary}\n{notes}"
    return figures + research


async def _design(ctx: PipelineContext, prompt: str) -> GenDocument | None:
    return coerce_document(await ctx.call(ctx.agents.designer, prompt, heartbeat=_HB))


async def _design_batched(ctx: PipelineContext) -> GenDocument | None:
    """One designer call per SCENE_BATCH beats; two consecutive dead batches
    stop generation (the provider is down, not unlucky)."""
    beats = ctx.plan.beats  # type: ignore[union-attr]
    doc = GenDocument(scenes=[])
    n_batches = (len(beats) + SCENE_BATCH - 1) // SCENE_BATCH
    dead = 0
    for start in range(0, len(beats), SCENE_BATCH):
        chunk = beats[start : start + SCENE_BATCH]
        batch_no = start // SCENE_BATCH + 1
        ctx.log(
            AgentId.VISUAL_DESIGNER,
            f"[Visual Designer] designing beats {start}–{start + len(chunk) - 1} "
            f"(batch {batch_no}/{n_batches})…",
        )
        beat_lines = "\n".join(f"- {b.headline} — {b.summary} (~{b.duration_ms} ms)" for b in chunk)
        continuity = ""
        if doc.scenes:
            tail = "\n".join(f"- {(s.narration or '')[:60]}" for s in doc.scenes[-3:])
            continuity = (
                f"\n\nScenes designed so far end with:\n{tail}\nKeep the SAME visual "
                "theme (background, palette, typography) so the video feels continuous."
            )
        prompt = (
            f"{ctx.brief}"
            f"Design scenes for ONLY these {len(chunk)} beats of the story plan "
            f"(other beats are designed separately). EXACTLY ONE scene per beat, "
            f'in beat order: return {len(chunk)} scenes as {{"scenes": [...]}} — '
            f"never merge or summarize beats.\n"
            f"Title: {ctx.title}\nAudience: {AudienceLevel(ctx.audience).value}\n"
            f"Language: {ctx.language}{_context_blocks(ctx)}\n\n"
            f"Beats:\n{beat_lines}{continuity}\n\nDocument text:\n{ctx.paper_text}"
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
                    "[Visual Designer] two consecutive batches failed — stopping batch generation",
                )
                break
    return doc if doc.scenes else None


async def _design_single_shot(ctx: PipelineContext) -> GenDocument | None:
    """Whole cut in one call — only for short videos / planless runs."""
    prompt = (
        f"{ctx.brief}"
        f"Design the explainer scenes for this document.\n"
        f"Title: {ctx.title}\nAudience: {AudienceLevel(ctx.audience).value}\n"
        f"Language: {ctx.language}{_context_blocks(ctx)}{plan_block(ctx.plan)}\n\n"
        f"Document text:\n{ctx.paper_text}"
    )
    try:
        return await _design(ctx, prompt)
    except Exception as exc:  # noqa: BLE001
        log.warning("single-shot design failed: %s", exc)
        return None


async def _fit_length(ctx: PipelineContext) -> None:
    """Designer-driven length fit: too short → ONLY new scenes spliced before
    the closer; too long → full revised list."""
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
            f"{ctx.target_ms / 1000:.0f}s target ({'too SHORT' if too_short else 'too LONG'}) "
            f"— asking for a fix (round {fit_round}/{ctx.tunables.length_fit_rounds})",
        )
        if too_short:
            summary = "\n".join(
                f"{i}: {(s.narration or '')[:60]}" for i, s in enumerate(doc.scenes)
            )
            prompt = (
                f"{ctx.brief}"
                f"Your cut totals {total_ms} ms but the video must total about "
                f"{ctx.target_ms} ms. Design NEW scenes (~{ctx.target_ms - total_ms} ms "
                f"more, grounded with citations) to slot between the existing scenes "
                f'and the closer. Return ONLY the new scenes as {{"scenes": [...]}} — '
                f"do NOT repeat existing scenes.\n\n"
                f"Existing scenes (index: narration):\n{summary}\n\n"
                f"Document text:\n{ctx.paper_text}"
            )
        else:
            from vyakhya.agents.schemas import scenes_json

            prompt = (
                f"{ctx.brief}"
                f"Your scene list totals {total_ms} ms but the video must total about "
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


async def _replan_if_still_short(ctx: PipelineContext) -> None:
    """Escalation: fit rounds can only pad the plan. A cut under 70% of target
    means the plan is too thin — planner writes NEW beats, designer renders
    only those (one pass)."""
    doc = ctx.doc
    assert doc is not None
    total_ms = sum(s.duration_ms for s in doc.scenes)
    if total_ms >= ctx.target_ms * 0.7:
        return
    missing_ms = ctx.target_ms - total_ms
    ctx.log(
        AgentId.VISUAL_DESIGNER,
        f"[Visual Designer] cut is still {total_ms / 1000:.0f}s vs "
        f"{ctx.target_ms / 1000:.0f}s — sending back to the planner for the "
        f"missing {missing_ms / 1000:.0f}s…",
    )
    summary = "\n".join(f"{i}: {(s.narration or '')[:60]}" for i, s in enumerate(doc.scenes))
    try:
        content = await ctx.call(
            ctx.agents.planner,
            f"{ctx.brief}"
            f"The current cut covers only {total_ms} ms of a {ctx.target_ms} ms video. "
            f"Plan about {max(2, missing_ms // 8000)} NEW beats (4000–9000 ms each, "
            f"~{missing_ms} ms total) covering document material the existing scenes "
            f"skip. Return ONLY the new beats.\n\n"
            f"Existing scenes (index: narration):\n{summary}\n\n"
            f"Document text:\n{ctx.paper_text}",
            heartbeat=_HB,
        )
        extra = coerce_plan(content)
    except Exception as exc:  # noqa: BLE001 - keep the cut
        log.warning("length re-plan failed: %s", exc)
        extra = None
    if extra is None:
        ctx.log(
            AgentId.VISUAL_DESIGNER, "[Visual Designer] re-plan produced no beats — keeping cut"
        )
        return
    new_scenes = []
    for start in range(0, len(extra.beats), SCENE_BATCH):
        chunk = extra.beats[start : start + SCENE_BATCH]
        beat_lines = "\n".join(f"- {b.headline} — {b.summary} (~{b.duration_ms} ms)" for b in chunk)
        try:
            part = await _design(
                ctx,
                f"{ctx.brief}"
                f"Design scenes for ONLY these new beats (they slot between your "
                f"existing scenes and the closer). EXACTLY ONE scene per beat: return "
                f'{len(chunk)} scenes as {{"scenes": [...]}}.\n\n'
                f"New beats:\n{beat_lines}\n\nDocument text:\n{ctx.paper_text}",
            )
        except Exception as exc:  # noqa: BLE001 - keep the cut
            log.warning("re-plan design failed: %s", exc)
            continue
        if part is not None and part.scenes:
            new_scenes.extend(part.scenes)
    if not new_scenes:
        ctx.log(
            AgentId.VISUAL_DESIGNER,
            "[Visual Designer] re-plan produced no usable scenes — keeping cut",
        )
        return
    for sc in new_scenes:
        sc.index = None
    if len(doc.scenes) > 1:
        doc.scenes = doc.scenes[:-1] + new_scenes + doc.scenes[-1:]
    else:
        doc.scenes = doc.scenes + new_scenes
    ctx.log(
        AgentId.VISUAL_DESIGNER,
        f"[Visual Designer] re-plan added {len(new_scenes)} scenes → "
        f"{len(doc.scenes)} total, "
        f"{sum(s.duration_ms for s in doc.scenes) / 1000:.0f}s",
    )


async def run(ctx: PipelineContext) -> None:
    async with ctx.stage(AgentId.VISUAL_DESIGNER, "Visual Designer"):
        if ctx.plan is not None and len(ctx.plan.beats) > SCENE_BATCH:
            ctx.doc = await _design_batched(ctx)
        else:
            ctx.doc = await _design_single_shot(ctx)
        if ctx.doc is None or not ctx.doc.scenes:
            ctx.log(AgentId.VISUAL_DESIGNER, "[Visual Designer] produced no valid scenes")
            raise RuntimeError("visual designer produced no scenes")
        ctx.log(AgentId.VISUAL_DESIGNER, f"[Visual Designer] produced {len(ctx.doc.scenes)} scenes")
        await _fit_length(ctx)
        await _replan_if_still_short(ctx)
        ctx.scenes_payload = dump_scenes(ctx.doc, ctx.figure_map)
