"""Unit tests for the agent sequence, simulated executor, and preview compile."""

from __future__ import annotations

from vyakhya.agents.events import AGENT_SEQUENCE
from vyakhya.agents.simulated import SimulatedPipelineExecutor
from vyakhya.enums import AgentId, PipelineEventType, VisualType
from vyakhya.schemas.project import SceneIn
from vyakhya.services.editor import compile_scene_preview
from vyakhya.services.pipeline import get_agent_sequence


def test_agent_sequence_order_and_length():
    ids = [a for a, _ in AGENT_SEQUENCE]
    assert ids[0] is AgentId.INGESTOR
    assert ids[-1] is AgentId.ASSEMBLER
    assert AgentId.VERIFIER in ids
    assert len(AGENT_SEQUENCE) == 7


def test_get_agent_sequence_dtos():
    seq = get_agent_sequence()
    assert len(seq) == 7
    assert seq[1].label == "Video Idea"


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


async def test_simulated_executor_emits_scenes():
    executor = SimulatedPipelineExecutor(step_seconds=0.0, log_seconds=0.0)
    events = [e async for e in executor.run("p1")]
    scene_events = [e for e in events if e["type"] == PipelineEventType.SCENES.value]
    assert len(scene_events) == 1
    scenes = scene_events[0]["payload"]
    assert isinstance(scenes, list) and len(scenes) >= 1
    for s in scenes:
        assert VisualType(s["visualType"])  # known visual type
        assert isinstance(s["params"], dict)
    assert events[-1]["type"] == PipelineEventType.DONE.value


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
