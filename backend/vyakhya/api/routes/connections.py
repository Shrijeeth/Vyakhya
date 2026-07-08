"""Model-config endpoints (docs/api.md → Model configuration)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from vyakhya.api.deps import SessionDep
from vyakhya.enums import AgentRole
from vyakhya.schemas.config import (
    AgentModelAssignmentOut,
    AssignmentUpdate,
    ConnectionCreate,
    ConnectionTest,
    ConnectionTestResult,
    ProviderConnectionOut,
)
from vyakhya.services import connections as svc
from vyakhya.services.probe import ProbeResult

router = APIRouter(tags=["model-config"])


def _result(probe: ProbeResult) -> ConnectionTestResult:
    return ConnectionTestResult(
        success=probe.success,
        latency_ms=probe.latency_ms,
        detail=probe.detail,
        error=probe.error,
    )


@router.get("/connections", response_model=list[ProviderConnectionOut])
async def list_connections(session: SessionDep) -> list[ProviderConnectionOut]:
    return [ProviderConnectionOut.model_validate(c) for c in await svc.list_connections(session)]


@router.post("/connections", response_model=ProviderConnectionOut, status_code=201)
async def create_connection(
    payload: ConnectionCreate, session: SessionDep
) -> ProviderConnectionOut:
    conn = await svc.create_connection(session, payload)
    return ProviderConnectionOut.model_validate(conn)


@router.delete("/connections/{connection_id}", status_code=204)
async def delete_connection(connection_id: str, session: SessionDep) -> Response:
    if not await svc.remove_connection(session, connection_id):
        raise HTTPException(status_code=404, detail="Connection not found")
    return Response(status_code=204)


@router.post("/connections/test", response_model=ConnectionTestResult)
async def test_connection_draft(
    payload: ConnectionTest, session: SessionDep
) -> ConnectionTestResult:
    """Probe an unsaved connection (add-connection form)."""
    return _result(await svc.probe_draft(session, payload))


@router.post("/connections/{connection_id}/test", response_model=ConnectionTestResult)
async def test_connection(connection_id: str, session: SessionDep) -> ConnectionTestResult:
    """Probe a saved connection and persist its status."""
    res = await svc.test_connection(session, connection_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    _conn, probe = res
    return _result(probe)


@router.get("/assignments", response_model=list[AgentModelAssignmentOut])
async def list_assignments(session: SessionDep) -> list[AgentModelAssignmentOut]:
    rows = await svc.list_assignments(session)
    return [AgentModelAssignmentOut.model_validate(r) for r in rows]


@router.put("/assignments/{role}", response_model=list[AgentModelAssignmentOut])
async def update_assignment(
    role: AgentRole, payload: AssignmentUpdate, session: SessionDep
) -> list[AgentModelAssignmentOut]:
    rows = await svc.update_assignment(session, role, payload.connection_id)
    return [AgentModelAssignmentOut.model_validate(r) for r in rows]
