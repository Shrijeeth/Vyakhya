"""Project listing / retrieval / creation."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.core.logging import get_logger
from vyakhya.db.models.project import Project
from vyakhya.enums import AspectRatio, AudienceLevel, ProjectStatus
from vyakhya.utils import new_id

log = get_logger(__name__)


async def list_projects(session: AsyncSession) -> list[Project]:
    result = await session.execute(select(Project).order_by(Project.updated_at.desc()))
    return list(result.scalars().all())


async def get_project(session: AsyncSession, project_id: str) -> Project | None:
    return await session.get(Project, project_id)


async def create_project(
    session: AsyncSession,
    *,
    filename: str,
    audience: AudienceLevel,
    aspect_ratio: AspectRatio,
    language: str,
    target_length_min: int,
    tts_enabled: bool = True,
    paper_file_url: str | None = None,
) -> Project:
    title = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    project = Project(
        id=new_id("p"),
        title=title,
        source_paper=filename,
        paper_file_url=paper_file_url,
        status=ProjectStatus.GENERATING,
        duration_ms=0,
        audience=audience,
        aspect_ratio=aspect_ratio,
        language=language,
        target_length_min=target_length_min,
        tts_enabled=tts_enabled,
    )
    session.add(project)
    await session.flush()
    log.info(
        "project created id=%s title=%r audience=%s aspect=%s lang=%s tts=%s",
        project.id,
        title,
        audience.value,
        aspect_ratio.value,
        language,
        tts_enabled,
    )
    return project


async def remove_project(session: AsyncSession, project_id: str) -> bool:
    """Delete a project (scenes/runs/flags cascade via FK ON DELETE CASCADE)."""
    project = await session.get(Project, project_id)
    if project is None:
        log.warning("project remove: not found id=%s", project_id)
        return False
    await session.delete(project)
    await session.flush()
    log.info("project removed id=%s", project_id)
    return True
