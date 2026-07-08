"""Unit tests for the agent sequence, simulated executor, and preview compile."""

from __future__ import annotations

from vyakhya.agents.pipeline import AGENT_SEQUENCE, SimulatedPipelineExecutor
from vyakhya.enums import AgentId, PipelineEventType, VisualType
from vyakhya.schemas.project import SceneIn
from vyakhya.services.editor import compile_scene_preview
from vyakhya.services.pipeline import get_agent_sequence


def test_agent_sequence_order_and_length():
    ids = [a for a, _ in AGENT_SEQUENCE]
    assert ids[0] is AgentId.INGESTOR
    assert ids[-1] is AgentId.ASSEMBLER
    assert AgentId.VERIFIER in ids
    assert len(AGENT_SEQUENCE) == 8


def test_get_agent_sequence_dtos():
    seq = get_agent_sequence()
    assert len(seq) == 8
    assert seq[1].label == "Comprehension"


async def test_simulated_executor_emits_status_flags_and_done():
    executor = SimulatedPipelineExecutor(step_seconds=0.0, log_seconds=0.0)
    events = [e async for e in executor.run("p1")]
    types = [e["type"] for e in events]
    assert types[0] == PipelineEventType.STATUS.value
    assert types[-1] == PipelineEventType.DONE.value
    flags = [e for e in events if e["type"] == PipelineEventType.FLAG.value]
    assert len(flags) == 3
    # progress reaches 1.0
    progress = [e["payload"] for e in events if e["type"] == PipelineEventType.PROGRESS.value]
    assert progress[-1] == 1.0


def test_compile_scene_preview_escapes_and_includes_type():
    scene = SceneIn(
        id="s1",
        index=2,
        narration="<script>alert(1)</script>",
        visual_type=VisualType.BULLET_REVEAL,
    )
    html = compile_scene_preview(scene)
    assert "bullet.reveal" in html
    assert "<script>alert" not in html  # escaped
    assert "Scene 2" in html
