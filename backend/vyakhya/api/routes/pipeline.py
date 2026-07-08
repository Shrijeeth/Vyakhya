"""Pipeline endpoints (docs/api.md → Pipeline streaming)."""

from __future__ import annotations

from functools import partial

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from vyakhya.api.deps import SessionDep
from vyakhya.api.sse import sse_response_with_producer
from vyakhya.schemas.pipeline import AgentSequenceItem, VerifierFlagOut
from vyakhya.services import pipeline as svc
from vyakhya.services import projects as projects_svc

router = APIRouter(tags=["pipeline"])


@router.get("/agents/sequence", response_model=list[AgentSequenceItem])
async def agent_sequence() -> list[AgentSequenceItem]:
    return svc.get_agent_sequence()


@router.get("/projects/{project_id}/pipeline/stream")
async def pipeline_stream(project_id: str, session: SessionDep) -> StreamingResponse:
    if await projects_svc.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    run_id = await svc.prepare_run(project_id)
    return sse_response_with_producer(run_id, partial(svc.launch_run, run_id, project_id))


@router.get("/projects/{project_id}/verifier-flags", response_model=list[VerifierFlagOut])
async def verifier_flags(project_id: str, session: SessionDep) -> list[VerifierFlagOut]:
    flags = await svc.list_verifier_flags(session, project_id)
    return [VerifierFlagOut.model_validate(f) for f in flags]
