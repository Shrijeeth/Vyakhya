"""Pipeline orchestration: create a run, drive the executor, persist events and
flags, and publish to the SSE broker.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.agents.pipeline import AGENT_SEQUENCE, SimulatedPipelineExecutor
from vyakhya.core.database import get_sessionmaker
from vyakhya.core.events import broker
from vyakhya.core.logging import get_logger
from vyakhya.db.models.pipeline import AgentNodeState, PipelineEvent, PipelineRun, VerifierFlag
from vyakhya.db.models.project import Project
from vyakhya.enums import AgentStatus, PipelineEventType, ProjectStatus, VerifierLevel
from vyakhya.schemas.pipeline import AgentSequenceItem
from vyakhya.utils import new_id, utcnow

log = get_logger(__name__)


def get_agent_sequence() -> list[AgentSequenceItem]:
    return [AgentSequenceItem(id=aid, label=label) for aid, label in AGENT_SEQUENCE]


async def list_verifier_flags(session: AsyncSession, project_id: str) -> list[VerifierFlag]:
    result = await session.execute(
        select(VerifierFlag)
        .where(VerifierFlag.project_id == project_id)
        .order_by(VerifierFlag.created_at.desc())
    )
    return list(result.scalars().all())


async def create_run(session: AsyncSession, project_id: str) -> PipelineRun:
    run = PipelineRun(id=new_id("run"), project_id=project_id, status=AgentStatus.RUNNING)
    session.add(run)
    await session.flush()  # insert the run before its FK-dependent node states
    for agent, label in AGENT_SEQUENCE:
        session.add(
            AgentNodeState(run_id=run.id, agent=agent, label=label, status=AgentStatus.QUEUED)
        )
    await session.flush()
    return run


async def prepare_run(project_id: str) -> str:
    """Persist a run row and return its id (also the SSE topic). Call
    `launch_run` after registering an SSE subscriber so no events are missed.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        run = await create_run(session, project_id)
        run_id = run.id
        await session.commit()
    return run_id


def launch_run(run_id: str, project_id: str) -> None:
    asyncio.create_task(_execute(run_id, project_id))


async def _execute(run_id: str, project_id: str) -> None:
    executor = SimulatedPipelineExecutor()
    sm = get_sessionmaker()
    try:
        async for event in executor.run(project_id):
            async with sm() as session:
                await _persist_event(session, run_id, project_id, event)
                await session.commit()
            await broker.publish(run_id, event)
        # Mark run + project complete.
        async with sm() as session:
            run = await session.get(PipelineRun, run_id)
            if run is not None:
                run.status = AgentStatus.DONE
                run.progress = 1.0
                run.finished_at = utcnow()
            project = await session.get(Project, project_id)
            if project is not None:
                project.status = ProjectStatus.READY
            await session.commit()
    except Exception:  # noqa: BLE001 - surface failures as an error status
        log.exception("pipeline run %s failed", run_id)
        async with sm() as session:
            run = await session.get(PipelineRun, run_id)
            if run is not None:
                run.status = AgentStatus.ERROR
                run.finished_at = utcnow()
            project = await session.get(Project, project_id)
            if project is not None:
                project.status = ProjectStatus.FAILED
            await session.commit()
        await broker.publish(
            run_id, {"type": PipelineEventType.DONE.value, "agentId": None, "payload": None}
        )
    finally:
        await broker.close(run_id)


async def _persist_event(session: AsyncSession, run_id: str, project_id: str, event: dict) -> None:
    etype = event["type"]
    agent = event.get("agentId")
    payload = event.get("payload")

    session.add(PipelineEvent(run_id=run_id, type=etype, agent=agent, payload={"value": payload}))

    if etype == PipelineEventType.STATUS.value and agent is not None:
        result = await session.execute(
            select(AgentNodeState).where(
                AgentNodeState.run_id == run_id, AgentNodeState.agent == agent
            )
        )
        node = result.scalar_one_or_none()
        if node is not None:
            node.status = AgentStatus(payload)
    elif etype == PipelineEventType.PROGRESS.value:
        run = await session.get(PipelineRun, run_id)
        if run is not None and isinstance(payload, int | float):
            run.progress = float(payload)
    elif etype == PipelineEventType.FLAG.value and isinstance(payload, dict):
        session.add(
            VerifierFlag(
                id=payload.get("id") or new_id("vf"),
                project_id=project_id,
                run_id=run_id,
                claim=payload["claim"],
                source_span=payload["sourceSpan"],
                level=VerifierLevel(payload["level"]),
                note=payload.get("note"),
            )
        )
