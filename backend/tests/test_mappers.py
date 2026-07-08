"""Unit tests for ORM → DTO mapping (no DB needed — in-memory ORM instances)."""

from __future__ import annotations

from datetime import UTC, datetime

from vyakhya.db.models.project import Project, Scene, SceneCitation
from vyakhya.enums import (
    AspectRatio,
    AudienceLevel,
    CaptionStyle,
    ProjectStatus,
    SceneTransition,
    VisualType,
)
from vyakhya.services.mappers import editor_project_to_dto, project_to_dto, scene_to_dto


def _scene(sid: str, pos: int, duration: int | None) -> Scene:
    s = Scene(
        id=sid,
        project_id="p1",
        position=pos,
        narration="hello",
        visual_type=VisualType.TITLE_CARD,
        params={"title": "x"},
        caption_style=CaptionStyle.MINIMAL,
        transition=SceneTransition.FADE,
        duration_ms=duration,
    )
    s.citations = [SceneCitation(id="c1", scene_id=sid, label="[1]", source_span="§1", position=0)]
    return s


def test_scene_to_dto_maps_position_and_auto_duration():
    dto = scene_to_dto(_scene("s1", 3, None))
    assert dto.index == 3
    assert dto.duration_ms == "auto"
    assert dto.citations[0].source_span == "§1"


def test_scene_to_dto_keeps_numeric_duration():
    assert scene_to_dto(_scene("s1", 1, 6000)).duration_ms == 6000


def test_project_to_dto_uses_thumbnail_url_alias():
    p = Project(
        id="p1",
        title="Paper",
        source_paper="Author, 2024",
        thumbnail_url="http://x/y.png",
        status=ProjectStatus.READY,
        audience=AudienceLevel.STUDENT,
        aspect_ratio=AspectRatio.WIDE,
        language="en",
        duration_ms=1000,
    )
    p.updated_at = datetime.now(UTC)
    dto = project_to_dto(p)
    assert dto.thumbnail == "http://x/y.png"
    assert dto.source_paper == "Author, 2024"


def test_editor_total_duration_sums_numeric_and_ignores_auto():
    p = Project(
        id="p1",
        title="Paper",
        source_paper="x",
        status=ProjectStatus.READY,
        audience=AudienceLevel.STUDENT,
        aspect_ratio=AspectRatio.WIDE,
        language="en",
        duration_ms=0,
    )
    p.scenes = [_scene("s1", 1, 6000), _scene("s2", 2, None), _scene("s3", 3, 4000)]
    dto = editor_project_to_dto(p)
    assert dto.total_duration_ms == 10000
    assert [s.index for s in dto.scenes] == [1, 2, 3]
