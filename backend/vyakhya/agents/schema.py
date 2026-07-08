"""Scene-JSON — the contract crossing Python ⇄ browser ⇄ render worker.

This is the canonical Pydantic definition (destined to be an Agno `output_schema`).
The TS type in `@vyakhya/compiler` is generated from this schema's JSON Schema
(CI checks for drift). Keep field names aligned with docs/api.md.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from vyakhya.enums import CaptionStyle, SceneTransition, VisualType


class SceneCitation(BaseModel):
    id: str
    label: str
    source_span: str = Field(serialization_alias="sourceSpan")


class SceneNode(BaseModel):
    id: str
    index: int
    narration: str
    visual_type: VisualType = Field(serialization_alias="visualType")
    params: dict[str, Any] = Field(default_factory=dict)
    caption_style: CaptionStyle = Field(
        default=CaptionStyle.MINIMAL, serialization_alias="captionStyle"
    )
    transition: SceneTransition = SceneTransition.FADE
    duration_ms: int | Literal["auto"] = Field(default="auto", serialization_alias="durationMs")
    citations: list[SceneCitation] = Field(default_factory=list)


class SceneDocument(BaseModel):
    """The whole editable video: an ordered list of scenes."""

    id: str
    title: str
    aspect_ratio: str = Field(serialization_alias="aspectRatio")
    scenes: list[SceneNode] = Field(default_factory=list)


def scene_document_json_schema() -> dict[str, Any]:
    """Expose the JSON Schema (source for the generated TS type)."""
    return SceneDocument.model_json_schema(by_alias=True)
