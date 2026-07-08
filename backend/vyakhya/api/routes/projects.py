"""Projects endpoints (docs/api.md → Projects)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from vyakhya.api.deps import SessionDep
from vyakhya.core.logging import get_logger
from vyakhya.enums import AspectRatio, AudienceLevel
from vyakhya.schemas.project import ProjectOut
from vyakhya.services import projects as svc
from vyakhya.services import storage
from vyakhya.services.mappers import project_to_dto

log = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(session: SessionDep) -> list[ProjectOut]:
    return [project_to_dto(p) for p in await svc.list_projects(session)]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, session: SessionDep) -> ProjectOut:
    project = await svc.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project_to_dto(project)


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    audience: Annotated[AudienceLevel, Form()],
    aspect_ratio: Annotated[AspectRatio, Form(alias="aspectRatio")],
    language: Annotated[str, Form()] = "en",
    target_length_min: Annotated[int, Form(alias="targetLengthMin")] = 3,
    tts_enabled: Annotated[bool, Form(alias="ttsEnabled")] = True,
) -> ProjectOut:
    # Extract the paper's text now so the agent pipeline designs from the
    # actual content; the original file goes to MinIO after the row exists.
    data = await file.read()
    paper_text = svc.extract_pdf_text(data)
    project = await svc.create_project(
        session,
        filename=file.filename or "untitled.pdf",
        paper_text=paper_text,
        audience=audience,
        aspect_ratio=aspect_ratio,
        language=language,
        target_length_min=target_length_min,
        tts_enabled=tts_enabled,
    )
    try:
        project.paper_file_url = await storage.put_paper(project.id, data)
    except Exception as exc:  # noqa: BLE001 - storage down shouldn't block creation
        log.warning("paper upload to object storage failed: %s", exc)
    return project_to_dto(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, session: SessionDep) -> Response:
    project = await svc.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    paper_url = project.paper_file_url
    await svc.remove_project(session, project_id)
    if paper_url:
        await storage.delete_object(paper_url)
    return Response(status_code=204)
