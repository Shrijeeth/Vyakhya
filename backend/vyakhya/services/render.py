"""Render settings (singleton) + render-job orchestration.

The executor is simulated (progress ticks) behind a clean seam; the real path
calls the Node `render/` service (`RENDER_SERVICE_URL`) and streams its progress.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

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
    return row


def _job_event(job: RenderJob) -> dict:
    return {
        "id": job.id,
        "status": job.status.value,
        "progress": job.progress,
        "outputUrl": job.output_url,
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
    return job_id


def launch_render(job_id: str) -> None:
    asyncio.create_task(_execute_render(job_id))


async def _execute_render(job_id: str) -> None:
    sm = get_sessionmaker()
    progress = 0.0
    try:
        async with sm() as session:
            job = await session.get(RenderJob, job_id)
            await broker.publish(job_id, _job_event(job))
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
