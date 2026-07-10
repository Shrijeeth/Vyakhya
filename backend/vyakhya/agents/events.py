"""Pipeline event vocabulary shared by every executor.

``AGENT_SEQUENCE`` is the fixed stage order the UI renders; ``pipeline_event``
is the wire shape of one stream event. ``PipelineExecutor`` is the interface
the service layer drives — any executor (real or simulated) is an async
iterator of these events.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from vyakhya.enums import AgentId, PipelineEventType

AGENT_SEQUENCE: list[tuple[AgentId, str]] = [
    (AgentId.INGESTOR, "Ingestor"),
    (AgentId.COMPREHENSION, "Comprehension"),
    (AgentId.PLANNER, "Planner"),
    (AgentId.SCRIPTWRITER, "Scriptwriter"),
    (AgentId.VISUAL_DESIGNER, "Visual Designer"),
    (AgentId.NARRATOR, "Narrator"),
    (AgentId.VERIFIER, "Reviewer"),
    (AgentId.ASSEMBLER, "Assembler"),
]


def pipeline_event(
    type_: PipelineEventType, payload: Any = None, agent: AgentId | None = None
) -> dict:
    return {"type": type_.value, "agentId": agent.value if agent else None, "payload": payload}


class PipelineExecutor(Protocol):
    def run(self, project_id: str) -> AsyncIterator[dict]:  # pragma: no cover - interface
        ...
