"""Unit tests for the Agno pipeline wiring (no network / no API keys).

Only the parts that don't require a live model: executor selection, the model
factory mapping, and the generation-schema → persistence-payload shape.
"""

from __future__ import annotations

import pytest

from vyakhya.agents.schemas import GenCitation, GenDocument, GenScene
from vyakhya.enums import CaptionStyle, ProviderId, SceneTransition, VisualType
from vyakhya.services.pipeline import _select_executor

pytest.importorskip("agno", reason="agents extra not installed")


def test_select_executor_defaults_to_simulated(monkeypatch):
    from vyakhya.agents.pipeline import SimulatedPipelineExecutor

    # use_agno defaults False → simulated.
    ex = _select_executor()
    assert isinstance(ex, SimulatedPipelineExecutor)


def test_select_executor_uses_agno_when_enabled(monkeypatch):
    from vyakhya.agents.executor import AgnoPipelineExecutor
    from vyakhya.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("USE_AGNO", "true")
    get_settings.cache_clear()
    try:
        ex = _select_executor()
        assert isinstance(ex, AgnoPipelineExecutor)
    finally:
        monkeypatch.delenv("USE_AGNO", raising=False)
        get_settings.cache_clear()


def test_model_factory_builds_each_llm_provider():
    from vyakhya.agents.model_factory import build_llm_model

    cases = [
        (ProviderId.OPENAI, "gpt-5.5"),
        (ProviderId.ANTHROPIC, "claude-opus-4-8"),
        (ProviderId.GEMINI, "gemini-3.1-pro"),
        (ProviderId.GROQ, "llama-3.3-70b-versatile"),
        (ProviderId.OLLAMA, "qwen3:30b"),
    ]
    for provider, model_id in cases:
        model = build_llm_model(provider, model_id, "fake-key")
        assert model.id == model_id


def test_model_factory_rejects_tts_provider():
    from vyakhya.agents.model_factory import build_llm_model

    with pytest.raises(ValueError, match="not an LLM provider"):
        build_llm_model(ProviderId.ELEVENLABS, "eleven_v3", "k")


def test_gen_scene_maps_to_persistence_payload():
    doc = GenDocument(
        scenes=[
            GenScene(
                narration="n",
                visual_type=VisualType.TITLE_CARD,
                params={"title": "T"},
                citations=[GenCitation(label="Abstract", source_span="§1")],
            )
        ]
    )
    payload = [s.model_dump(by_alias=True) for s in doc.scenes]
    s = payload[0]
    # Keys must match what services.pipeline._persist_scenes reads.
    assert s["visualType"] == "title.card"
    assert s["captionStyle"] == CaptionStyle.MINIMAL.value
    assert s["transition"] == SceneTransition.FADE.value
    assert s["durationMs"] == 6000
    assert s["citations"][0]["sourceSpan"] == "§1"


def test_skills_load():
    from vyakhya.agents.skills import get_hyperframes_skills

    skills = get_hyperframes_skills()
    names = skills.get_skill_names()
    assert "hyperframes" in names
    assert "hyperframes-core" in names


def test_coerce_plan_from_json_and_bare_list():
    from vyakhya.agents.schemas import coerce_plan as _coerce_plan

    plan = _coerce_plan('{"beats": [{"headline": "Hook", "durationMs": 8000}]}')
    assert plan is not None and plan.beats[0].headline == "Hook"
    # Bare array without the {"beats": ...} wrapper.
    plan = _coerce_plan('[{"headline": "A"}, {"headline": "B", "index": 3}]')
    assert plan is not None and len(plan.beats) == 2
    assert plan.beats[1].index == 3
    # Garbage and empty plans are rejected.
    assert _coerce_plan("not json") is None
    assert _coerce_plan('{"beats": []}') is None


def test_plan_block_renders_beats():
    from vyakhya.agents.schemas import StoryPlan
    from vyakhya.agents.steps.plan import plan_block as _plan_block

    assert _plan_block(None) == ""
    plan = StoryPlan.model_validate(
        {"beats": [{"headline": "Hook", "summary": "the opening", "durationMs": 7000}]}
    )
    block = _plan_block(plan)
    assert "0: Hook — the opening (~7000 ms)" in block


def test_scene_lenient_cosmetic_enums():
    s = GenScene.model_validate(
        {
            "narration": "x",
            "visualType": "custom.html",
            "captionStyle": "mono-lower-third",
            "transition": "whip-pan",
        }
    )
    assert s.caption_style is CaptionStyle.MINIMAL
    assert s.transition is SceneTransition.FADE


def test_designer_skill_text_inlined():
    from vyakhya.agents.skills import get_designer_skill_text

    text = get_designer_skill_text()
    assert "Skill: hyperframes-core" in text
    assert "Skill: faceless-explainer" in text
    assert len(text) > 10_000


def test_pipeline_workflow_builds():
    from vyakhya.agents.context import PipelineContext, Tunables
    from vyakhya.agents.workflow import build_pipeline_workflow

    ctx = PipelineContext(
        project_id="p1",
        title="t",
        audience="layperson",
        language="en",
        target_min=3,
        tts_enabled=False,
        aspect="16:9",
        user_prompt="",
        paper_text="text",
        figures=[],
        paper_file_url=None,
        tunables=Tunables(),
        agents=None,
        emit=lambda e: None,
    )
    wf = build_pipeline_workflow(ctx)
    assert [s.name for s in wf.steps] == [
        "ingest",
        "research",
        "plan",
        "design",
        "review",
        "assemble",
    ]
