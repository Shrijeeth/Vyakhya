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


_MAX_PAPER_CHARS = 200_000


def extract_pdf_text(data: bytes) -> str | None:
    """Best-effort text extraction from uploaded PDF bytes (pypdf, `agents`
    extra). Returns None when pypdf is unavailable or the PDF is unreadable —
    the pipeline then degrades to title-only design."""
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        return text[:_MAX_PAPER_CHARS] or None
    except ModuleNotFoundError:
        log.warning("pypdf not installed (agents extra) — paper text not extracted")
        return None
    except Exception as exc:  # noqa: BLE001 - a bad PDF shouldn't block project creation
        log.warning("PDF text extraction failed: %s", exc)
        return None


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
    paper_text: str | None = None,
    user_prompt: str | None = None,
) -> Project:
    title = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    project = Project(
        id=new_id("p"),
        title=title,
        source_paper=filename,
        paper_file_url=paper_file_url,
        paper_text=paper_text,
        user_prompt=user_prompt or None,
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
