"""Render settings (singleton) + render-job orchestration.

The executor is simulated (progress ticks) behind a clean seam; the real path
calls the Node `render/` service (`RENDER_SERVICE_URL`) and streams its progress.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.core.config import get_settings
from vyakhya.core.database import get_sessionmaker
from vyakhya.core.events import broker
from vyakhya.core.logging import get_logger
from vyakhya.db.models.render import RenderJob, RenderSettings
from vyakhya.enums import RenderStatus
from vyakhya.schemas.render import RenderSettingsIO
from vyakhya.utils import new_id, utcnow

log = get_logger(__name__)

_SAMPLE_OUTPUT = (
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
)


async def get_render_settings(session: AsyncSession) -> RenderSettings:
    row = await session.get(RenderSettings, True)
    if row is None:
        row = RenderSettings(id=True)
        session.add(row)
        await session.flush()
    return row


async def save_render_settings(session: AsyncSession, payload: RenderSettingsIO) -> RenderSettings:
    row = await get_render_settings(session)
    row.fps = payload.fps
    row.width = payload.width
    row.height = payload.height
    row.quality = payload.quality
    row.format = payload.format
    row.codec = payload.codec
    row.gpu = payload.gpu
    row.workers = payload.workers
    row.audio_master_db = payload.audio_master_db
    row.audio_narration_db = payload.audio_narration_db
    row.audio_music_db = payload.audio_music_db
    await session.flush()
    log.info(
        "render settings saved fps=%s %sx%s codec=%s",
        row.fps,
        row.width,
        row.height,
        row.codec.value,
    )
    return row


def _job_event(job: RenderJob) -> dict:
    return {
        "id": job.id,
        "status": job.status.value,
        "progress": job.progress,
        "outputUrl": job.output_url,
        "error": job.error,
    }


async def prepare_render(project_id: str, settings: RenderSettingsIO) -> str:
    """Persist a render job and return its id (SSE topic). Call `launch_render`
    after registering an SSE subscriber.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        job = RenderJob(
            id=new_id("r"),
            project_id=project_id,
            status=RenderStatus.RUNNING,
            progress=0.0,
            settings=settings.model_dump(by_alias=True),
        )
        session.add(job)
        await session.commit()
        job_id = job.id
    log.info("render job prepared job=%s project=%s", job_id, project_id)
    return job_id


async def launch_render(job_id: str) -> None:
    """Start the render as a background job: deferred to the Procrastinate
    worker when INPROCESS_JOBS=false, else an in-process task. The job row is
    the source of truth — progress survives page reloads and reconnects."""
    if not get_settings().inprocess_jobs:
        try:
            from vyakhya.worker import ensure_open

            job_app = await ensure_open()
            await job_app.configure_task("vyakhya.run_render").defer_async(job_id=job_id)
            log.info("render job deferred to worker job=%s", job_id)
            return
        except Exception:  # noqa: BLE001 - queue down → degrade to in-process
            log.exception("deferring render %s to worker failed; running in-process", job_id)
    log.info("render job launched in-process job=%s", job_id)
    asyncio.create_task(_execute_render(job_id))


async def list_renders(session: AsyncSession, project_id: str) -> list[RenderJob]:
    result = await session.execute(
        select(RenderJob)
        .where(RenderJob.project_id == project_id)
        .order_by(RenderJob.created_at.desc())
        .limit(20)
    )
    return list(result.scalars().all())


async def stream_render_job(job_id: str) -> AsyncIterator[dict]:
    """Yield the job's state by polling its row — emits on every change and
    ends at a terminal status. Works whichever process executes the render."""
    sm = get_sessionmaker()
    last: dict | None = None
    while True:
        async with sm() as session:
            job = await session.get(RenderJob, job_id)
        if job is None:
            break
        event = _job_event(job)
        if event != last:
            yield event
            last = event
        if job.status in (RenderStatus.DONE, RenderStatus.ERROR):
            break
        await asyncio.sleep(0.5)


async def fail_orphaned_renders() -> None:
    """On startup (in-process mode only), fail render jobs left RUNNING by a
    dead process — they can never finish."""
    if not get_settings().inprocess_jobs:
        return
    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(RenderJob).where(RenderJob.status == RenderStatus.RUNNING)
        )
        jobs = list(result.scalars().all())
        for job in jobs:
            job.status = RenderStatus.ERROR
            job.error = "interrupted by a server restart"
            job.finished_at = utcnow()
        await session.commit()
    if jobs:
        log.warning("marked %d orphaned render job(s) as error", len(jobs))


async def _execute_render(job_id: str) -> None:
    sm = get_sessionmaker()
    try:
        async with sm() as session:
            job = await session.get(RenderJob, job_id)
            project_id = job.project_id if job else None
            settings_dict = dict(job.settings) if job else {}
            await broker.publish(job_id, _job_event(job))

        if get_settings().use_render_service and project_id:
            await _render_via_service(job_id, project_id, settings_dict)
        else:
            await _render_simulated(job_id)
    except Exception:  # noqa: BLE001
        log.exception("render job %s failed", job_id)
        async with sm() as session:
            job = await session.get(RenderJob, job_id)
            if job is not None:
                job.status = RenderStatus.ERROR
                job.finished_at = utcnow()
                await session.commit()
                await broker.publish(job_id, _job_event(job))
    finally:
        await broker.close(job_id)


async def _render_simulated(job_id: str) -> None:
    """In-process progress ticks (no Chrome/FFmpeg) — dev default."""
    sm = get_sessionmaker()
    progress = 0.0
    while progress < 1.0:
        await asyncio.sleep(0.5)
        progress = min(1.0, progress + 0.08)
        async with sm() as session:
            job = await session.get(RenderJob, job_id)
            if job is None:
                return
            if progress >= 1.0:
                job.status = RenderStatus.DONE
                job.progress = 1.0
                job.output_url = _SAMPLE_OUTPUT
                job.finished_at = utcnow()
            else:
                job.progress = progress
            await session.commit()
            await broker.publish(job_id, _job_event(job))


async def _render_via_service(job_id: str, project_id: str, settings_dict: dict) -> None:
    """Delegate to the Node render service; map its progress onto the job row."""
    from vyakhya.services.render_client import build_scene_document, stream_render_service

    doc = await build_scene_document(project_id)
    if not doc or not doc.get("scenes"):
        # Nothing to render yet — fall back so the UI still completes.
        await _render_simulated(job_id)
        return

    sm = get_sessionmaker()
    async for event in stream_render_service(doc, settings_dict):
        async with sm() as session:
            job = await session.get(RenderJob, job_id)
            if job is None:
                return
            status = event.get("status")
            if status == "error":
                job.status = RenderStatus.ERROR
                job.error = event.get("error")
                job.finished_at = utcnow()
            elif status == "done":
                job.status = RenderStatus.DONE
                job.progress = 1.0
                job.output_url = event.get("outputUrl")
                job.finished_at = utcnow()
            else:
                job.progress = float(event.get("progress", 0.0))
            await session.commit()
            await broker.publish(job_id, _job_event(job))
