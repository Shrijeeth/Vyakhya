"""Verifier step: fact verification, then visual review with EYES.

Fact loop: the verifier grounds every claim in the document; failures go
back to the designer as index-carrying partial revisions. When the rounds
run out with fails standing, the planner writes replacement beats and the
designer rebuilds those scenes from scratch, then one extra re-check.

Visual loop: the render service screenshots every scene and a vision
reviewer judges the actual frames; flagged scenes go back to the designer
with concrete CSS fixes until approval, stall, or the round cap."""

from __future__ import annotations

from vyakhya.agents.context import PipelineContext
from vyakhya.agents.schemas import (
    DesignReviewReport,
    GenVerifierFlag,
    VerifierReport,
    coerce_document,
    coerce_model,
    coerce_plan,
    dump_scenes,
    scenes_json,
)
from vyakhya.core.logging import get_logger
from vyakhya.enums import AgentId
from vyakhya.utils import new_id

log = get_logger(__name__)

_HB = (AgentId.VERIFIER, "Verifier")
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

    async with ctx.stage(AgentId.VERIFIER, "Verifier"):
        await _verify_facts(ctx)
        await _review_visuals(ctx)
        ctx.scenes_payload = dump_scenes(ctx.doc, ctx.figure_map)  # type: ignore[arg-type]


# ── Fact verification ──────────────────────────────────────────────────────────
async def _check(ctx: PipelineContext) -> VerifierReport | None:
    try:
        content = await ctx.call(
            ctx.agents.verifier,
            f"Verify these scenes against the document.\n\n"
            f"Scenes:\n{scenes_json(ctx.doc)}\n\nDocument text:\n{ctx.paper_text}",  # type: ignore[arg-type]
            heartbeat=_HB,
            attempts=1,
        )
        return coerce_model(content, VerifierReport)  # type: ignore[return-value]
    except Exception as exc:  # noqa: BLE001 - verification is best-effort
        log.warning("verifier failed: %s", exc)
        return None


def _emit_flags(ctx: PipelineContext, report: VerifierReport) -> list[GenVerifierFlag]:
    for flag in report.flags:
        payload = flag.model_dump(by_alias=True)
        payload["id"] = new_id("vf")
        ctx.flag(AgentId.VERIFIER, payload)
    return [f for f in report.flags if f.level == "fail"]


async def _revise(ctx: PipelineContext, prompt: str) -> int:
    """One designer revision; returns how many scenes were patched in place."""
    from vyakhya.agents.schemas import patch_scenes

    try:
        revised = coerce_document(await ctx.call(ctx.agents.designer, prompt, heartbeat=_HB))
    except Exception as exc:  # noqa: BLE001 - keep current doc
        log.warning("designer revision failed: %s", exc)
        revised = None
    if revised is None or not revised.scenes:
        return 0
    return patch_scenes(ctx.doc, revised)  # type: ignore[arg-type]


async def _verify_facts(ctx: PipelineContext) -> None:
    rounds = ctx.tunables.verifier_rounds
    for round_no in range(1, rounds + 2):  # +1 re-check round after escalation
        report = await _check(ctx)
        if report is None:
            ctx.log(AgentId.VERIFIER, "[Verifier] verifier unavailable — proceeding")
            return
        fails = _emit_flags(ctx, report)
        ctx.log(
            AgentId.VERIFIER,
            f"[Verifier] round {round_no}: {len(report.flags)} claims checked, {len(fails)} failed",
        )
        if report.approved and not fails:
            ctx.log(AgentId.VERIFIER, "[Verifier] approved")
            return
        if round_no > rounds:
            ctx.log(
                AgentId.VERIFIER,
                f"[Verifier] proceeding with {len(fails)} unresolved flag(s)",
            )
            return
        fail_lines = "\n".join(
            f"- {f.claim} ({f.source_span}): {f.note or f.level}"
            for f in report.flags
            if f.level != "pass"
        )
        if round_no == rounds:
            prompt = await _replacement_prompt(ctx, fail_lines)
            if prompt is None:
                ctx.log(
                    AgentId.VERIFIER,
                    f"[Verifier] re-plan produced no replacement beats — proceeding "
                    f"with {len(fails)} unresolved flag(s)",
                )
                return
        else:
            ctx.log(AgentId.VERIFIER, "[Verifier] sending scenes back to the designer…")
            prompt = (
                f"{ctx.brief}"
                f"Revise your scenes. The verifier rejected them.\n\n"
                f"Verifier notes:\n{report.revision_notes}\n\n"
                f"Flagged claims:\n{fail_lines}\n\n"
                f"Current scenes:\n{scenes_json(ctx.doc)}\n\n"  # type: ignore[arg-type]
                f"Fix ONLY what was flagged, grounding every claim in the document. "
                f"If a scene is wrong at its core, REDESIGN it (new narration AND "
                f"html/css). Return ONLY the scenes you changed, each carrying its "
                f'0-based "index".\n\nDocument text:\n{ctx.paper_text}'
            )
        patched = await _revise(ctx, prompt)
        if patched:
            ctx.log(
                AgentId.VERIFIER,
                f"[Verifier] designer revised {patched} scene(s) in place "
                f"(cut stays {len(ctx.doc.scenes)} scenes)",  # type: ignore[union-attr]
            )
        else:
            ctx.log(AgentId.VERIFIER, "[Verifier] revision produced no applicable scenes")
            if round_no == rounds:
                return


async def _replacement_prompt(ctx: PipelineContext, fail_lines: str) -> str | None:
    """Escalation: planner writes replacement beats for the failing scenes;
    the designer rebuilds them from scratch."""
    ctx.log(
        AgentId.VERIFIER,
        "[Verifier] revision rounds exhausted — sending the failing scenes back to the planner…",
    )
    summary = "\n".join(
        f"{i}: {(s.narration or '')[:60]}"
        for i, s in enumerate(ctx.doc.scenes)  # type: ignore[union-attr]
    )
    try:
        content = await ctx.call(
            ctx.agents.planner,
            f"{ctx.brief}"
            f"These claims failed fact verification:\n{fail_lines}\n\n"
            f"Scenes (index: narration):\n{summary}\n\n"
            f"Write a replacement beat for EACH scene carrying a failed claim, "
            f'grounded ONLY in the document, each carrying the 0-based "index" of '
            f"the scene it replaces.\n\nDocument text:\n{ctx.paper_text}",
            heartbeat=_HB,
        )
        rplan = coerce_plan(content)
    except Exception as exc:  # noqa: BLE001 - keep the cut
        log.warning("verifier re-plan failed: %s", exc)
        rplan = None
    beats = [
        b
        for b in (rplan.beats if rplan is not None else [])
        if b.index is not None and 0 <= b.index < len(ctx.doc.scenes)  # type: ignore[union-attr]
    ]
    if not beats:
        return None
    beat_lines = "\n".join(
        f"- index {b.index}: {b.headline} — {b.summary} (~{b.duration_ms} ms)" for b in beats
    )
    return (
        f"{ctx.brief}"
        f"REDESIGN these scenes from scratch per the new beats — new narration AND "
        f"a new html/css visual, every claim grounded in the document. Return ONLY "
        f'the redesigned scenes, each carrying its 0-based "index".\n\n'
        f"New beats:\n{beat_lines}\n\nDocument text:\n{ctx.paper_text}"
    )


# ── Visual review (screenshots) ────────────────────────────────────────────────
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


async def _review_visuals(ctx: PipelineContext) -> None:
    prev_majors: int | None = None
    stalled = 0
    for vround in range(1, ctx.tunables.visual_max_rounds + 1):
        ctx.scenes_payload = dump_scenes(ctx.doc, ctx.figure_map)  # type: ignore[arg-type]
        try:
            images = await _screenshots(ctx)
        except Exception as exc:  # noqa: BLE001 - degrade, don't block
            log.warning("scene screenshots unavailable: %s", exc)
            ctx.log(AgentId.VERIFIER, "[Verifier] visual review skipped (screenshots unavailable)")
            return
        if not images:
            ctx.log(AgentId.VERIFIER, "[Verifier] visual review skipped (no screenshots)")
            return
        ctx.log(
            AgentId.VERIFIER,
            f"[Verifier] visual round {vround}: reviewing {len(images)} scene screenshot(s)…",
        )
        scene_lines = "\n".join(
            f"{i}: {s.get('visualType')} — {(s.get('narration') or '')[:70]}"
            for i, s in enumerate(ctx.scenes_payload)
        )
        brief_note = (
            f"The user's creative brief (frames MUST honor it):\n{ctx.user_prompt}\n\n"
            if ctx.user_prompt
            else ""
        )
        try:
            content = await ctx.call(
                ctx.agents.reviewer,
                f"Review these rendered scene screenshots (in scene order, 0-based).\n\n"
                f"{brief_note}Scenes:\n{scene_lines}",
                images=images,
                heartbeat=_HB,
                attempts=1,
            )
            report = coerce_model(content, DesignReviewReport)
        except Exception as exc:  # noqa: BLE001 - review is best-effort
            log.warning("design review round %d failed: %s", vround, exc)
            report = None
        if report is None:
            ctx.log(AgentId.VERIFIER, "[Verifier] visual reviewer unavailable — proceeding")
            return
        # Blind round: the endpoint dropped the image parts; acting on it
        # would send the designer phantom fixes.
        blind = [i for i in report.issues if any(m in i.problem.lower() for m in _BLIND_MARKERS)]
        if report.issues and len(blind) * 2 >= len(report.issues):
            ctx.log(
                AgentId.VERIFIER,
                f"[Verifier] visual round {vround}: reviewer did not receive the "
                f"screenshots — skipping this round",
            )
            return
        majors = [i for i in report.issues if i.severity == "major"]
        for issue in report.issues:
            ctx.flag(
                AgentId.VERIFIER,
                {
                    "id": new_id("vf"),
                    "claim": f"scene {issue.scene_index}: {issue.problem}",
                    "sourceSpan": f"scene {issue.scene_index} (visual)",
                    "level": "fail" if issue.severity == "major" else "warn",
                    "note": issue.fix,
                },
            )
        ctx.log(
            AgentId.VERIFIER,
            f"[Verifier] visual round {vround}: {len(report.issues)} issue(s), {len(majors)} major",
        )
        if report.approved and not majors:
            ctx.log(AgentId.VERIFIER, "[Verifier] visual design approved")
            return
        if prev_majors is not None and len(majors) >= prev_majors:
            stalled += 1
        else:
            stalled = 0
        prev_majors = len(majors)
        if stalled >= ctx.tunables.visual_stall_rounds:
            ctx.log(
                AgentId.VERIFIER,
                f"[Verifier] {stalled} review rounds with no progress — proceeding "
                f"with {len(majors)} unresolved issue(s)",
            )
            return
        issue_lines = "\n".join(
            f"- scene {i.scene_index} [{i.severity}]: {i.problem} → FIX: {i.fix}"
            for i in report.issues
        )
        patched = await _revise(
            ctx,
            f"{ctx.brief}"
            f"The art director reviewed SCREENSHOTS of your rendered scenes and "
            f"rejected the cut. Fix EXACTLY the flagged scenes' html/css (layout, "
            f"overlap, sizing, backgrounds).\n\nIssues:\n{issue_lines}\n\n"
            f"Current scenes:\n{scenes_json(ctx.doc)}\n\n"  # type: ignore[arg-type]
            f"Return ONLY the fixed scenes, each carrying its 0-based "
            f'"index" — do NOT resend unchanged scenes.',
        )
        if patched:
            ctx.log(
                AgentId.VERIFIER,
                f"[Verifier] designer fixed {patched} scene(s) in place "
                f"(cut stays {len(ctx.doc.scenes)} scenes)",  # type: ignore[union-attr]
            )
        else:
            ctx.log(AgentId.VERIFIER, "[Verifier] visual revision not applicable — proceeding")
            return
    ctx.log(AgentId.VERIFIER, "[Verifier] visual round cap reached — proceeding")
