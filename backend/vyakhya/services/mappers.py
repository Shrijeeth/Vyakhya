"""ORM → DTO mapping helpers (the parts Pydantic `from_attributes` can't infer)."""

from __future__ import annotations

from vyakhya.db.models.project import Project, Scene
from vyakhya.schemas.project import (
    EditorProjectOut,
    ProjectOut,
    SceneCitationOut,
    SceneOut,
)


def project_to_dto(p: Project) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        title=p.title,
        source_paper=p.source_paper,
        thumbnail=p.thumbnail_url,
        status=p.status,
        duration_ms=p.duration_ms,
        updated_at=p.updated_at,
        audience=p.audience,
        aspect_ratio=p.aspect_ratio,
        language=p.language,
    )


def scene_to_dto(s: Scene) -> SceneOut:
    return SceneOut(
        id=s.id,
        index=s.position,
        narration=s.narration,
        visual_type=s.visual_type,
        params=s.params or {},
        caption_style=s.caption_style,
        transition=s.transition,
        duration_ms="auto" if s.duration_ms is None else s.duration_ms,
        citations=[
            SceneCitationOut(id=c.id, label=c.label, source_span=c.source_span) for c in s.citations
        ],
    )


def editor_project_to_dto(p: Project) -> EditorProjectOut:
    scenes = [scene_to_dto(s) for s in p.scenes]
    total = sum(0 if s.duration_ms == "auto" else int(s.duration_ms) for s in scenes)
    return EditorProjectOut(
        id=p.id,
        title=p.title,
        scenes=scenes,
        total_duration_ms=total,
        aspect_ratio=p.aspect_ratio,
    )
