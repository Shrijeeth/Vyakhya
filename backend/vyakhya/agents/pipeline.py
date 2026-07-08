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


# Sample scenes the assembler "produces" for the simulated run — a short
# Transformer-paper explainer that exercises several visual types so the editor
# and preview have real content end-to-end. Params match the @vyakhya/compiler
# renderer shapes. The real Agno crew replaces this with Scene-JSON output.
_SAMPLE_SCENES: list[dict[str, Any]] = [
    {
        "visualType": "title.card",
        "narration": "Attention Is All You Need — a look at the Transformer architecture.",
        "params": {"title": "The Transformer", "subtitle": "Attention Is All You Need"},
        "durationMs": 5000,
        "citations": [{"label": "Title", "sourceSpan": "p. 1"}],
    },
    {
        "visualType": "bullet.reveal",
        "narration": "It drops recurrence entirely and relies on self-attention.",
        "params": {
            "bullets": [
                "No recurrence or convolution",
                "Self-attention over the whole sequence",
                "Highly parallelizable training",
            ]
        },
        "durationMs": 7000,
        "citations": [{"label": "Abstract", "sourceSpan": "§1, p. 2"}],
    },
    {
        "visualType": "equation.build",
        "narration": "Scaled dot-product attention weights values by query-key similarity.",
        "params": {
            "latex": (
                r"\mathrm{Attention}(Q,K,V)="
                r"\mathrm{softmax}\!\left(\frac{QK^\top}{\sqrt{d_k}}\right)V"
            )
        },
        "durationMs": 8000,
        "citations": [{"label": "Eq. 1", "sourceSpan": "§3.2.1, p. 4"}],
    },
    {
        "visualType": "diagram.attention",
        "narration": "Each token attends to every other token in the sequence.",
        "params": {"tokens": ["The", "cat", "sat", "on", "the", "mat"]},
        "durationMs": 6000,
        "citations": [{"label": "Fig. 2", "sourceSpan": "§3.2, p. 4"}],
    },
    {
        "visualType": "dataviz.bar",
        "narration": "It set a new state of the art on WMT 2014 translation.",
        "params": {
            "series": [
                {"label": "ByteNet", "value": 23.75},
                {"label": "GNMT", "value": 24.6},
                {"label": "Transformer", "value": 28.4},
            ]
        },
        "durationMs": 7000,
        "citations": [{"label": "Table 2", "sourceSpan": "§6.1, p. 8"}],
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
            if agent is AgentId.ASSEMBLER:
                # The assembler emits the final Scene-JSON; the service persists it.
                yield _event(PipelineEventType.SCENES, _SAMPLE_SCENES, agent)
        yield _event(PipelineEventType.DONE, None)
