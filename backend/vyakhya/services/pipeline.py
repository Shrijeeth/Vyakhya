"""Pipeline orchestration: create a run, drive the executor, persist events and
flags, and publish to the SSE broker.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.agents.pipeline import AGENT_SEQUENCE, SimulatedPipelineExecutor
from vyakhya.core.config import get_settings
from vyakhya.core.database import get_sessionmaker
from vyakhya.core.events import broker
from vyakhya.core.logging import get_logger
from vyakhya.db.models.pipeline import AgentNodeState, PipelineEvent, PipelineRun, VerifierFlag
from vyakhya.db.models.project import Project, Scene, SceneCitation
from vyakhya.enums import (
    AgentStatus,
    CaptionStyle,
    PipelineEventType,
    ProjectStatus,
    SceneTransition,
    VerifierLevel,
    VisualType,
)
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
    log.info("pipeline run prepared run=%s project=%s", run_id, project_id)
    return run_id


def launch_run(run_id: str, project_id: str) -> None:
    log.info("pipeline run launched run=%s project=%s", run_id, project_id)
    asyncio.create_task(_execute(run_id, project_id))


def _select_executor():  # noqa: ANN202 - PipelineExecutor (Agno or simulated)
    """Real Agno crew when USE_AGNO is on and the extra is importable; otherwise
    the simulated executor. Falls back if Agno can't be constructed."""
    if get_settings().use_agno:
        try:
            import agno  # noqa: F401 - probe the optional extra is installed

            from vyakhya.agents.agno_executor import AgnoPipelineExecutor

            log.info("pipeline using Agno executor")
            return AgnoPipelineExecutor()
        except Exception:  # noqa: BLE001 - missing extra / import error → simulate
            log.exception("Agno executor unavailable; falling back to simulated")
    return SimulatedPipelineExecutor()


async def _execute(run_id: str, project_id: str) -> None:
    executor = _select_executor()
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
        log.info("pipeline run done run=%s project=%s", run_id, project_id)
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
    elif etype == PipelineEventType.SCENES.value and isinstance(payload, list):
        await _persist_scenes(session, project_id, payload)


async def _persist_scenes(session: AsyncSession, project_id: str, scenes: list[dict]) -> None:
    """Replace the project's scenes with the assembler's output (idempotent re-run)."""
    await session.execute(delete(Scene).where(Scene.project_id == project_id))
    total_ms = 0
    for pos, s in enumerate(scenes):
        duration = s.get("durationMs")
        if isinstance(duration, int):
            total_ms += duration
        scene = Scene(
            id=new_id("s"),
            project_id=project_id,
            position=pos,
            narration=s.get("narration", ""),
            visual_type=VisualType(s["visualType"]),
            params=s.get("params", {}),
            caption_style=CaptionStyle(s.get("captionStyle", CaptionStyle.MINIMAL.value)),
            transition=SceneTransition(s.get("transition", SceneTransition.FADE.value)),
            duration_ms=duration if isinstance(duration, int) else None,
        )
        for cpos, c in enumerate(s.get("citations", [])):
            scene.citations.append(
                SceneCitation(
                    id=new_id("c"),
                    label=c["label"],
                    source_span=c["sourceSpan"],
                    position=cpos,
                )
            )
        session.add(scene)
    project = await session.get(Project, project_id)
    if project is not None:
        project.duration_ms = total_ms
    log.info(
        "scenes persisted project=%s count=%d duration_ms=%d", project_id, len(scenes), total_ms
    )
