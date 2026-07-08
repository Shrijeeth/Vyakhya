"""Pipeline endpoints (docs/api.md → Pipeline streaming)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from vyakhya.api.deps import SessionDep
from vyakhya.api.sse import sse_events_response
from vyakhya.enums import AgentStatus
from vyakhya.schemas.pipeline import AgentSequenceItem, VerifierFlagOut
from vyakhya.services import pipeline as svc
from vyakhya.services import projects as projects_svc

router = APIRouter(tags=["pipeline"])


@router.get("/agents/sequence", response_model=list[AgentSequenceItem])
async def agent_sequence() -> list[AgentSequenceItem]:
    return svc.get_agent_sequence()


@router.get("/projects/{project_id}/pipeline/stream")
async def pipeline_stream(
    project_id: str, session: SessionDep, restart: bool = False
) -> StreamingResponse:
    """Idempotent stream of the project's pipeline (events come from the
    persisted event log, so this works whether the run executes in-process or
    in the Procrastinate worker).

    - a run is in flight → follow it (replay persisted events, then poll live);
      reconnects, page refreshes, and double-mounts never spawn a second run.
    - latest run finished and not `restart` → replay it and end.
    - no run yet, or `restart=true` with nothing in flight → start a new run.
    """
    if await projects_svc.get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    run = await svc.latest_run(session, project_id)
    if run is None or (restart and run.status != AgentStatus.RUNNING):
        run_id = await svc.prepare_run(project_id)
        await svc.launch_run(run_id, project_id)
    else:
        run_id = run.id
    return sse_events_response(svc.stream_run_events(run_id))


@router.get("/projects/{project_id}/verifier-flags", response_model=list[VerifierFlagOut])
async def verifier_flags(project_id: str, session: SessionDep) -> list[VerifierFlagOut]:
    flags = await svc.list_verifier_flags(session, project_id)
    return [VerifierFlagOut.model_validate(f) for f in flags]
