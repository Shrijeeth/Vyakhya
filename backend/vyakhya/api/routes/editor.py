"""Editor endpoints (docs/api.md → Editor)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from vyakhya.api.deps import SessionDep
from vyakhya.schemas.project import EditorProjectOut, SceneIn, SceneOut, ScenePreviewOut
from vyakhya.services import editor as svc
from vyakhya.services.mappers import editor_project_to_dto, scene_to_dto

router = APIRouter(prefix="/projects", tags=["editor"])


@router.get("/{project_id}/editor", response_model=EditorProjectOut)
async def get_editor_project(project_id: str, session: SessionDep) -> EditorProjectOut:
    project = await svc.get_editor_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return editor_project_to_dto(project)


@router.put("/{project_id}/scenes/{scene_id}", response_model=SceneOut)
async def save_scene(
    project_id: str, scene_id: str, scene: SceneIn, session: SessionDep
) -> SceneOut:
    if scene.id != scene_id:
        raise HTTPException(status_code=400, detail="Scene id mismatch")
    saved = await svc.save_scene(session, project_id, scene)
    if saved is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene_to_dto(saved)


@router.post("/{project_id}/scenes/{scene_id}/preview", response_model=ScenePreviewOut)
async def compile_preview(
    project_id: str, scene_id: str, scene: SceneIn, session: SessionDep
) -> ScenePreviewOut:
    return ScenePreviewOut(html=svc.compile_scene_preview(scene))
