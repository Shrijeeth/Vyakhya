"""Projects endpoints (docs/api.md → Projects)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from vyakhya.api.deps import SessionDep
from vyakhya.enums import AspectRatio, AudienceLevel
from vyakhya.schemas.project import ProjectOut
from vyakhya.services import projects as svc
from vyakhya.services.mappers import project_to_dto

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
) -> ProjectOut:
    # NOTE: file persistence to MinIO/S3 and pipeline kickoff land at this seam.
    project = await svc.create_project(
        session,
        filename=file.filename or "untitled.pdf",
        audience=audience,
        aspect_ratio=aspect_ratio,
        language=language,
        target_length_min=target_length_min,
    )
    return project_to_dto(project)
