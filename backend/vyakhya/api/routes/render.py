"""Render endpoints (docs/api.md → Render).

Rendering is a background job: POST starts it and returns the job row
immediately; progress is read from GET /renders/{id}/stream (SSE over the
persisted job state, safe across reloads) or GET /projects/{id}/renders.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from vyakhya.api.deps import SessionDep
from vyakhya.api.sse import sse_events_response
from vyakhya.db.models.render import RenderJob
from vyakhya.schemas.render import RenderJobOut, RenderSettingsIO
from vyakhya.services import projects as projects_svc
from vyakhya.services import render as svc

router = APIRouter(tags=["render"])


@router.get("/render/settings", response_model=RenderSettingsIO)
async def get_render_settings(session: SessionDep) -> RenderSettingsIO:
    return RenderSettingsIO.model_validate(await svc.get_render_settings(session))


@router.put("/render/settings", response_model=RenderSettingsIO)
async def save_render_settings(payload: RenderSettingsIO, session: SessionDep) -> RenderSettingsIO:
    return RenderSettingsIO.model_validate(await svc.save_render_settings(session, payload))


@router.post("/projects/{project_id}/render", response_model=RenderJobOut, status_code=202)
async def start_render(
    project_id: str, session: SessionDep, payload: RenderSettingsIO | None = None
) -> RenderJobOut:
    """Start a background render for the project. Omitting the payload uses the
    saved global defaults."""
    if await projects_svc.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = payload
    if settings is None:
        settings = RenderSettingsIO.model_validate(await svc.get_render_settings(session))
    job_id = await svc.prepare_render(project_id, settings)
    await svc.launch_render(job_id)
    job = await session.get(RenderJob, job_id)
    return RenderJobOut.model_validate(job)


@router.get("/projects/{project_id}/renders", response_model=list[RenderJobOut])
async def list_renders(project_id: str, session: SessionDep) -> list[RenderJobOut]:
    if await projects_svc.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return [RenderJobOut.model_validate(j) for j in await svc.list_renders(session, project_id)]


@router.get("/renders/{job_id}/stream")
async def render_stream(job_id: str, session: SessionDep) -> StreamingResponse:
    if await session.get(RenderJob, job_id) is None:
        raise HTTPException(status_code=404, detail="Render job not found")
    return sse_events_response(svc.stream_render_job(job_id))
