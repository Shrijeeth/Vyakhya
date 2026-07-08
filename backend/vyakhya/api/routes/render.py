"""Render endpoints (docs/api.md → Render)."""

from __future__ import annotations

from functools import partial

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from vyakhya.api.deps import SessionDep
from vyakhya.api.sse import sse_response_with_producer
from vyakhya.schemas.render import RenderSettingsIO
from vyakhya.services import projects as projects_svc
from vyakhya.services import render as svc

router = APIRouter(tags=["render"])


@router.get("/render/settings", response_model=RenderSettingsIO)
async def get_render_settings(session: SessionDep) -> RenderSettingsIO:
    return RenderSettingsIO.model_validate(await svc.get_render_settings(session))


@router.put("/render/settings", response_model=RenderSettingsIO)
async def save_render_settings(payload: RenderSettingsIO, session: SessionDep) -> RenderSettingsIO:
    return RenderSettingsIO.model_validate(await svc.save_render_settings(session, payload))


@router.post("/projects/{project_id}/render")
async def start_render(
    project_id: str, payload: RenderSettingsIO, session: SessionDep
) -> StreamingResponse:
    if await projects_svc.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    job_id = await svc.prepare_render(project_id, payload)
    return sse_response_with_producer(job_id, partial(svc.launch_render, job_id))
