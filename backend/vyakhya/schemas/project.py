"""Project + editor DTOs (docs/api.md → Projects, Editor)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from vyakhya.enums import (
    AspectRatio,
    AudienceLevel,
    CaptionStyle,
    ProjectStatus,
    SceneTransition,
    VisualType,
)
from vyakhya.schemas.common import CamelModel


class ProjectOut(CamelModel):
    id: str
    title: str
    source_paper: str
    thumbnail: str | None = None
    status: ProjectStatus
    duration_ms: int
    updated_at: datetime
    audience: AudienceLevel
    aspect_ratio: AspectRatio
    language: str


class SceneCitationOut(CamelModel):
    id: str
    label: str
    source_span: str


class SceneOut(CamelModel):
    id: str
    index: int
    narration: str
    visual_type: VisualType
    params: dict[str, Any]
    caption_style: CaptionStyle
    transition: SceneTransition
    # number of ms, or the string "auto"
    duration_ms: int | Literal["auto"]
    citations: list[SceneCitationOut]


class SceneIn(CamelModel):
    """Body for PUT /projects/:id/scenes/:sceneId (a full Scene)."""

    id: str
    index: int
    narration: str = ""
    visual_type: VisualType
    params: dict[str, Any] = Field(default_factory=dict)
    caption_style: CaptionStyle = CaptionStyle.MINIMAL
    transition: SceneTransition = SceneTransition.FADE
    duration_ms: int | Literal["auto"] = "auto"
    citations: list[SceneCitationOut] = Field(default_factory=list)


class EditorProjectOut(CamelModel):
    id: str
    title: str
    scenes: list[SceneOut]
    total_duration_ms: int
    aspect_ratio: AspectRatio


class ScenePreviewOut(CamelModel):
    html: str
