"""Unit tests for wire (camelCase) serialization + parsing of DTOs."""

from __future__ import annotations

from datetime import UTC, datetime

from vyakhya.enums import AspectRatio, AudienceLevel, ProjectStatus
from vyakhya.schemas.config import ConnectionCreate
from vyakhya.schemas.project import ProjectOut, SceneIn


def test_project_out_serializes_camelcase():
    dto = ProjectOut(
        id="p1",
        title="t",
        source_paper="sp",
        status=ProjectStatus.READY,
        duration_ms=42,
        updated_at=datetime.now(UTC),
        audience=AudienceLevel.STUDENT,
        aspect_ratio=AspectRatio.WIDE,
        language="en",
    )
    data = dto.model_dump(by_alias=True)
    assert "sourcePaper" in data and "durationMs" in data and "aspectRatio" in data
    assert data["aspectRatio"] == "16:9"


def test_scene_in_accepts_camelcase_and_defaults_auto():
    scene = SceneIn.model_validate(
        {
            "id": "s1",
            "index": 1,
            "narration": "n",
            "visualType": "title.card",
            "params": {"title": "x"},
            "captionStyle": "bold",
            "transition": "cut",
            "citations": [],
        }
    )
    assert scene.visual_type.value == "title.card"
    assert scene.duration_ms == "auto"  # default when omitted


def test_connection_create_maps_api_key_alias():
    c = ConnectionCreate.model_validate(
        {"provider": "openai", "model": "gpt-4o", "apiKey": "sk-123", "baseUrl": None}
    )
    assert c.api_key == "sk-123"
    assert c.provider.value == "openai"
