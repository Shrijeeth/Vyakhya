"""Review step: screenshots → issues routed to the right stage.

Each round the reviewer sees the rendered frames, the Scene Creator's
descriptions, the scenes' JSON, and the document, and tags every issue as
scene-level (the CONCEPT is wrong → Scene Creator rewrites the description,
then the Designer rebuilds it) or design-level (the EXECUTION is wrong →
the Designer fixes the html/css). Stops on approval, stall, or round cap."""

from __future__ import annotations

from vyakhya.agents.context import PipelineContext
from vyakhya.agents.schemas import (
    ReviewIssue,
    ReviewReport,
    coerce_document,
    coerce_model,
    dump_scenes,
    patch_scenes,
    scenes_json,
)
from vyakhya.agents.steps.design import build_prompt, design
from vyakhya.agents.steps.outline import create_scene
from vyakhya.core.logging import get_logger
from vyakhya.enums import AgentId
from vyakhya.utils import new_id

log = get_logger(__name__)

_HB = (AgentId.VERIFIER, "Reviewer")
_BLIND_MARKERS = ("no visual content", "no screenshot", "missing rendered", "no image")


async def run(ctx: PipelineContext) -> None:
    # The narrator stage is part of the UI sequence; audio happens at assemble.
    async with ctx.stage(AgentId.NARRATOR, "Narrator"):
        ctx.log(
            AgentId.NARRATOR,
            "[Narrator] "
            + (
                "narration audio will be synthesized once the cut is final (assembler)"
                if ctx.tts_enabled
                else "TTS is off for this project — no narration audio"
            ),
        )

    async with ctx.stage(AgentId.VERIFIER, "Reviewer"):
        await _review_loop(ctx)
        ctx.scenes_payload = dump_scenes(ctx.doc, ctx.figure_map)  # type: ignore[arg-type]


async def _screenshots(ctx: PipelineContext) -> list:
    """Per-scene screenshots as Agno images for the vision reviewer."""
    import base64

    from agno.media import Image as AgnoImage

    from vyakhya.services.render_client import capture_scene_screenshots

    shot_doc = {
        "id": ctx.project_id,
        "title": ctx.title,
        "aspectRatio": ctx.aspect,
        "scenes": [{"id": f"rev{i}", **s, "index": i} for i, s in enumerate(ctx.scenes_payload)],
    }
    shots = await capture_scene_screenshots(shot_doc)
    return [
        AgnoImage(content=base64.b64decode(s["png"]), format="png")
        for s in shots
        if isinstance(s.get("png"), str)
    ]


async def _get_report(ctx: PipelineContext, rnd: int) -> ReviewReport | None:
    try:
        images = await _screenshots(ctx)
    except Exception as exc:  # noqa: BLE001 - degrade, don't block
        log.warning("scene screenshots unavailable: %s", exc)
        images = []
    if not images:
        ctx.log(AgentId.VERIFIER, "[Reviewer] review skipped (no screenshots)")
        return None
    ctx.log(
        AgentId.VERIFIER,
        f"[Reviewer] round {rnd}: reviewing {len(images)} scene screenshot(s)…",
    )
    outline_block = "\n\n".join(f"### Scene {i + 1}\n{spec}" for i, spec in enumerate(ctx.outline))
    brief_note = (
        f"The user's creative brief (the video MUST honor it):\n{ctx.user_prompt}\n\n"
        if ctx.user_prompt
        else ""
    )
    try:
        content = await ctx.call(
            ctx.agents.reviewer,
            f"Review this explainer video. Screenshots are in scene order "
            f"(0-based).\n\n{brief_note}"
            f"Scene descriptions (what each scene SHOULD be):\n{outline_block}\n\n"
            f"Scenes as built (narration + html/css — check for real animation):\n"
            f"{scenes_json(ctx.doc)}\n\n"  # type: ignore[arg-type]
            f"Source document:\n{ctx.paper_text[:30_000]}",
            images=images,
            heartbeat=_HB,
            attempts=1,
        )
        report = coerce_model(content, ReviewReport)
    except Exception as exc:  # noqa: BLE001 - review is best-effort
        log.warning("review round %d failed: %s", rnd, exc)
        report = None
    if report is None:
        ctx.log(AgentId.VERIFIER, "[Reviewer] reviewer unavailable — proceeding")
        return None
    blind = [i for i in report.issues if any(m in i.problem.lower() for m in _BLIND_MARKERS)]
    if report.issues and len(blind) * 2 >= len(report.issues):
        ctx.log(
            AgentId.VERIFIER,
            f"[Reviewer] round {rnd}: reviewer did not receive the screenshots — "
            f"skipping this round",
        )
        return None
    return report


async def _fix_scene_level(ctx: PipelineContext, issues: list[ReviewIssue]) -> int:
    """Scene Creator rewrites the flagged descriptions, then the Designer
    rebuilds exactly those scenes (index-carrying patches)."""
    fixed = 0
    rebuilt: list[tuple[int, str]] = []
    for issue in issues:
        i = issue.scene_index
        if not (0 <= i < len(ctx.outline)):
            continue
        note = (
            f"\nThe reviewer rejected this scene's current version:\n"
            f"Problem: {issue.problem}\nFix: {issue.fix}\n"
            f"Its current description was:\n{ctx.outline[i]}\n"
            f"Rewrite the scene description to fix this."
        )
        try:
            scene = await create_scene(
                ctx, i, len(ctx.outline), ctx.outline[i - 1] if i > 0 else None, note
            )
        except Exception as exc:  # noqa: BLE001 - keep the old description
            log.warning("scene rewrite %d failed: %s", i, exc)
            scene = None
        if scene:
            ctx.outline[i] = scene
            rebuilt.append((i, scene))
    if not rebuilt:
        return 0
    prompt = build_prompt(
        ctx,
        rebuilt,
        " Keep the SAME visual theme as the other scenes. Each returned scene "
        'must carry the 0-based "index" of the scene it replaces: '
        + ", ".join(str(i) for i, _ in rebuilt)
        + ".",
    )
    try:
        revised = await design(ctx, prompt)
    except Exception as exc:  # noqa: BLE001 - keep current scenes
        log.warning("scene-level rebuild failed: %s", exc)
        revised = None
    if revised is not None and revised.scenes:
        # If the reply didn't carry indexes, map it onto the rebuilt slots.
        if all(sc.index is None for sc in revised.scenes):
            for (i, _), sc in zip(rebuilt, revised.scenes, strict=False):
                sc.index = i
        fixed = patch_scenes(ctx.doc, revised)  # type: ignore[arg-type]
    return fixed


async def _fix_design_level(ctx: PipelineContext, issues: list[ReviewIssue]) -> int:
    issue_lines = "\n".join(
        f"- scene {i.scene_index} [{i.severity}]: {i.problem} → FIX: {i.fix}" for i in issues
    )
    try:
        revised = coerce_document(
            await ctx.call(
                ctx.agents.designer,
                f"{ctx.brief}"
                f"The reviewer rejected the cut. Fix EXACTLY the flagged scenes — "
                f"real motion across the whole scene, clean layout, faithful to "
                f"each scene's description.\n\nIssues:\n{issue_lines}\n\n"
                f"Current scenes:\n{scenes_json(ctx.doc)}\n\n"  # type: ignore[arg-type]
                f"Return ONLY the fixed scenes, each carrying its 0-based "
                f'"index" — do NOT resend unchanged scenes.',
                heartbeat=_HB,
            )
        )
    except Exception as exc:  # noqa: BLE001 - keep current doc
        log.warning("design-level fix failed: %s", exc)
        revised = None
    if revised is None or not revised.scenes:
        return 0
    return patch_scenes(ctx.doc, revised)  # type: ignore[arg-type]


async def _review_loop(ctx: PipelineContext) -> None:
    prev_majors: int | None = None
    stalled = 0
    for rnd in range(1, ctx.tunables.review_rounds + 1):
        ctx.scenes_payload = dump_scenes(ctx.doc, ctx.figure_map)  # type: ignore[arg-type]
        report = await _get_report(ctx, rnd)
        if report is None:
            return
        majors = [i for i in report.issues if i.severity == "major"]
        for issue in report.issues:
            ctx.flag(
                AgentId.VERIFIER,
                {
                    "id": new_id("vf"),
                    "claim": f"scene {issue.scene_index}: {issue.problem}",
                    "sourceSpan": f"scene {issue.scene_index} ({issue.stage})",
                    "level": "fail" if issue.severity == "major" else "warn",
                    "note": issue.fix,
                },
            )
        scene_issues = [i for i in majors if i.stage == "scene"]
        design_issues = [i for i in majors if i.stage == "design"]
        ctx.log(
            AgentId.VERIFIER,
            f"[Reviewer] round {rnd}: {len(report.issues)} issue(s) — "
            f"{len(scene_issues)} scene-level, {len(design_issues)} design-level major",
        )
        if report.approved and not majors:
            ctx.log(AgentId.VERIFIER, "[Reviewer] approved")
            return
        if prev_majors is not None and len(majors) >= prev_majors:
            stalled += 1
        else:
            stalled = 0
        prev_majors = len(majors)
        if stalled >= ctx.tunables.review_stall_rounds:
            ctx.log(
                AgentId.VERIFIER,
                f"[Reviewer] {stalled} rounds with no progress — proceeding with "
                f"{len(majors)} unresolved issue(s)",
            )
            return
        patched = 0
        if scene_issues:
            n = await _fix_scene_level(ctx, scene_issues)
            patched += n
            ctx.log(
                AgentId.VERIFIER,
                f"[Reviewer] scene creator rewrote + designer rebuilt {n} scene(s)",
            )
        if design_issues:
            n = await _fix_design_level(ctx, design_issues)
            patched += n
            ctx.log(AgentId.VERIFIER, f"[Reviewer] designer fixed {n} scene(s) in place")
        if not patched:
            ctx.log(AgentId.VERIFIER, "[Reviewer] no fixes applied — proceeding")
            return
    ctx.log(AgentId.VERIFIER, "[Reviewer] round cap reached — proceeding")
