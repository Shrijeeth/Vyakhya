"""Review step: ONE simple loop.

Each round: screenshot every scene → the reviewer judges motion + visuals +
facts (it sees the frames, the scenes' css, and the document) → flagged
scenes go back to the designer as index-carrying patches. Stops on
approval, stall (majors not decreasing), or the round cap."""

from __future__ import annotations

from vyakhya.agents.context import PipelineContext
from vyakhya.agents.schemas import (
    ReviewReport,
    coerce_document,
    coerce_model,
    dump_scenes,
    patch_scenes,
    scenes_json,
)
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


async def _review_loop(ctx: PipelineContext) -> None:
    prev_majors: int | None = None
    stalled = 0
    for rnd in range(1, ctx.tunables.review_rounds + 1):
        ctx.scenes_payload = dump_scenes(ctx.doc, ctx.figure_map)  # type: ignore[arg-type]
        try:
            images = await _screenshots(ctx)
        except Exception as exc:  # noqa: BLE001 - degrade, don't block
            log.warning("scene screenshots unavailable: %s", exc)
            images = []
        if not images:
            ctx.log(AgentId.VERIFIER, "[Reviewer] review skipped (no screenshots)")
            return
        ctx.log(
            AgentId.VERIFIER,
            f"[Reviewer] round {rnd}: reviewing {len(images)} scene screenshot(s)…",
        )
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
                f"Scenes (narration + html/css — check for real animation):\n"
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
            return
        # Blind round: the endpoint dropped the image parts.
        blind = [i for i in report.issues if any(m in i.problem.lower() for m in _BLIND_MARKERS)]
        if report.issues and len(blind) * 2 >= len(report.issues):
            ctx.log(
                AgentId.VERIFIER,
                f"[Reviewer] round {rnd}: reviewer did not receive the screenshots "
                f"— skipping this round",
            )
            return
        majors = [i for i in report.issues if i.severity == "major"]
        for issue in report.issues:
            ctx.flag(
                AgentId.VERIFIER,
                {
                    "id": new_id("vf"),
                    "claim": f"scene {issue.scene_index}: {issue.problem}",
                    "sourceSpan": f"scene {issue.scene_index}",
                    "level": "fail" if issue.severity == "major" else "warn",
                    "note": issue.fix,
                },
            )
        ctx.log(
            AgentId.VERIFIER,
            f"[Reviewer] round {rnd}: {len(report.issues)} issue(s), {len(majors)} major",
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
        issue_lines = "\n".join(
            f"- scene {i.scene_index} [{i.severity}]: {i.problem} → FIX: {i.fix}"
            for i in report.issues
        )
        try:
            revised = coerce_document(
                await ctx.call(
                    ctx.agents.designer,
                    f"{ctx.brief}"
                    f"The reviewer rejected the cut. Fix EXACTLY the flagged scenes — "
                    f"real motion across the whole scene, clean layout, claims grounded "
                    f"in the document.\n\nIssues:\n{issue_lines}\n\n"
                    f"Current scenes:\n{scenes_json(ctx.doc)}\n\n"  # type: ignore[arg-type]
                    f"Return ONLY the fixed scenes, each carrying its 0-based "
                    f'"index" — do NOT resend unchanged scenes.\n\n'
                    f"Document text:\n{ctx.paper_text}",
                    heartbeat=_HB,
                )
            )
        except Exception as exc:  # noqa: BLE001 - keep current doc
            log.warning("review revision failed: %s", exc)
            revised = None
        patched = (
            patch_scenes(ctx.doc, revised)  # type: ignore[arg-type]
            if revised is not None and revised.scenes
            else 0
        )
        if patched:
            ctx.log(
                AgentId.VERIFIER,
                f"[Reviewer] designer fixed {patched} scene(s) in place "
                f"(cut stays {len(ctx.doc.scenes)} scenes)",  # type: ignore[union-attr]
            )
        else:
            ctx.log(AgentId.VERIFIER, "[Reviewer] revision not applicable — proceeding")
            return
    ctx.log(AgentId.VERIFIER, "[Reviewer] round cap reached — proceeding")
