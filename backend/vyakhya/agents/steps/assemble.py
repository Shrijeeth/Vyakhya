"""Assembler step: report the final cut and synthesize narration audio
against it (so revisions can't orphan clips)."""

from __future__ import annotations

import asyncio

from vyakhya.agents.context import PipelineContext
from vyakhya.agents.schemas import dump_scenes
from vyakhya.core.database import get_sessionmaker
from vyakhya.core.logging import get_logger
from vyakhya.enums import AgentId

log = get_logger(__name__)


async def run(ctx: PipelineContext) -> None:
    async with ctx.stage(AgentId.ASSEMBLER, "Assembler"):
        doc = ctx.doc
        assert doc is not None
        total_ms = sum(s.duration_ms for s in doc.scenes)
        ctx.log(
            AgentId.ASSEMBLER,
            f"[Assembler] final cut: {len(doc.scenes)} scenes, "
            f"{total_ms / 1000:.0f}s (target {ctx.target_min} min)",
        )
        if ctx.tts_enabled:
            await _narrate(ctx)
        ctx.scenes_payload = dump_scenes(doc, ctx.figure_map)
        ctx.scenes(AgentId.ASSEMBLER)


async def _narrate(ctx: PipelineContext) -> None:
    try:
        from vyakhya.services.tts import narrate_scene, resolve_tts_connection

        sm = get_sessionmaker()
        async with sm() as session:
            tts = await resolve_tts_connection(session)
        if tts is None:
            ctx.log(
                AgentId.ASSEMBLER,
                "[Assembler] TTS is on but no TTS connection is configured — "
                "add one in Model Config; skipping narration audio",
            )
            return
        conn, key = tts
        doc = ctx.doc
        assert doc is not None
        todo = [
            (i, s, (s.narration or "").strip())
            for i, s in enumerate(doc.scenes)
            if (s.narration or "").strip()
        ]
        ctx.log(
            AgentId.ASSEMBLER,
            f"[Assembler] synthesizing narration for {len(todo)} scene(s) "
            f"via {conn.provider} ({conn.model})…",
        )
        sem = asyncio.Semaphore(4)

        async def voice(i: int, text: str):  # noqa: ANN202
            async with sem:
                return await narrate_scene(ctx.project_id, i, text, conn, key)

        results = await asyncio.gather(
            *(voice(i, text) for i, _, text in todo), return_exceptions=True
        )
        voiced = 0
        for (i, scene, _), res in zip(todo, results, strict=True):
            if isinstance(res, BaseException):
                log.warning("TTS failed for scene %d: %s", i, res)
                continue
            url, ms = res
            scene.params.audio_url = url
            scene.params.audio_duration_ms = ms
            if ms and scene.duration_ms < ms + 300:
                scene.duration_ms = min(ms + 500, 60_000)
            voiced += 1
        ctx.log(
            AgentId.ASSEMBLER,
            f"[Assembler] narration audio attached to {voiced}/{len(todo)} scene(s)",
        )
    except Exception as exc:  # noqa: BLE001 - audio is an enhancement
        log.warning("narration synthesis failed: %s", exc)
        ctx.log(AgentId.ASSEMBLER, f"[Assembler] narration synthesis skipped: {exc}")
