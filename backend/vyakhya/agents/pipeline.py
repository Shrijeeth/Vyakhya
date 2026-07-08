"""The agent-crew pipeline seam.

`AGENT_SEQUENCE` is the fixed order the UI renders. `PipelineExecutor` is the
interface the service layer drives; `SimulatedPipelineExecutor` mirrors the
frontend mock (status → logs → done, with verifier flags) so the whole app runs
end-to-end today. The real Agno implementation (`AgnoPipelineExecutor`) drops in
behind the same async-iterator contract — no route/service changes.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol

from vyakhya.enums import AgentId, AgentStatus, PipelineEventType
from vyakhya.utils import new_id

AGENT_SEQUENCE: list[tuple[AgentId, str]] = [
    (AgentId.INGESTOR, "Ingestor"),
    (AgentId.COMPREHENSION, "Comprehension"),
    (AgentId.PLANNER, "Planner"),
    (AgentId.SCRIPTWRITER, "Scriptwriter"),
    (AgentId.VISUAL_DESIGNER, "Visual Designer"),
    (AgentId.NARRATOR, "Narrator"),
    (AgentId.VERIFIER, "Verifier"),
    (AgentId.ASSEMBLER, "Assembler"),
]


def _event(type_: PipelineEventType, payload: Any = None, agent: AgentId | None = None) -> dict:
    return {"type": type_.value, "agentId": agent.value if agent else None, "payload": payload}


# Sample verifier output for the simulated run (mirrors the frontend mock).
_SAMPLE_FLAGS = [
    {
        "id": "vf1",
        "claim": "Self-attention has O(n²) complexity in sequence length.",
        "sourceSpan": "§3.2, p. 4, ¶ 2",
        "level": "pass",
    },
    {
        "id": "vf2",
        "claim": "Transformer trained in 12 hours on 8 P100 GPUs.",
        "sourceSpan": "§5.1, p. 7",
        "level": "warn",
        "note": "Paper reports 12h for base model; large model took 3.5 days.",
    },
    {
        "id": "vf3",
        "claim": "Positional encodings are learned, not fixed.",
        "sourceSpan": "§3.5",
        "level": "fail",
        "note": "Paper uses fixed sinusoidal encodings for the base configuration.",
    },
]


class PipelineExecutor(Protocol):
    def run(self, project_id: str) -> AsyncIterator[dict]:  # pragma: no cover - interface
        ...


class SimulatedPipelineExecutor:
    """Deterministic, fast simulation of the agent crew for dev + preview."""

    def __init__(self, step_seconds: float = 0.4, log_seconds: float = 0.12) -> None:
        self.step_seconds = step_seconds
        self.log_seconds = log_seconds

    async def run(self, project_id: str) -> AsyncIterator[dict]:
        total = len(AGENT_SEQUENCE)
        for idx, (agent, label) in enumerate(AGENT_SEQUENCE):
            yield _event(PipelineEventType.STATUS, AgentStatus.RUNNING.value, agent)
            for step in range(1, 4):
                await asyncio.sleep(self.log_seconds)
                yield _event(PipelineEventType.LOG, f"[{label}] step {step}/3 …", agent)
            await asyncio.sleep(self.step_seconds)
            yield _event(PipelineEventType.STATUS, AgentStatus.DONE.value, agent)
            yield _event(PipelineEventType.PROGRESS, round((idx + 1) / total, 3))
            if agent is AgentId.VERIFIER:
                for flag in _SAMPLE_FLAGS:
                    yield _event(PipelineEventType.FLAG, {**flag, "id": new_id("vf")})
        yield _event(PipelineEventType.DONE, None)
