"""Projects, scenes, and scene citations — the Scene-JSON source of truth."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from vyakhya.core.database import Base
from vyakhya.db.types import pg_enum
from vyakhya.enums import (
    AspectRatio,
    AudienceLevel,
    CaptionStyle,
    ProjectStatus,
    SceneTransition,
    VisualType,
)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_paper: Mapped[str] = mapped_column(Text, nullable=False)
    paper_file_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        pg_enum(ProjectStatus, "project_status"),
        nullable=False,
        default=ProjectStatus.DRAFT,
    )
    audience: Mapped[AudienceLevel] = mapped_column(
        pg_enum(AudienceLevel, "audience_level"), nullable=False
    )
    aspect_ratio: Mapped[AspectRatio] = mapped_column(
        pg_enum(AspectRatio, "aspect_ratio"), nullable=False, default=AspectRatio.WIDE
    )
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    target_length_min: Mapped[int | None] = mapped_column(Integer)
    # Whether the narrator (TTS) stage runs — chosen at project creation.
    tts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    scenes: Mapped[list[Scene]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Scene.position",
    )


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("project_id", "position", name="uq_scene_position"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    narration: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visual_type: Mapped[VisualType] = mapped_column(
        pg_enum(VisualType, "visual_type"), nullable=False
    )
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    caption_style: Mapped[CaptionStyle] = mapped_column(
        pg_enum(CaptionStyle, "caption_style"), nullable=False, default=CaptionStyle.MINIMAL
    )
    transition: Mapped[SceneTransition] = mapped_column(
        pg_enum(SceneTransition, "scene_transition"), nullable=False, default=SceneTransition.FADE
    )
    # NULL == "auto"
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="scenes")
    citations: Mapped[list[SceneCitation]] = relationship(
        back_populates="scene",
        cascade="all, delete-orphan",
        order_by="SceneCitation.position",
    )


class SceneCitation(Base):
    __tablename__ = "scene_citations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    source_span: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    scene: Mapped[Scene] = relationship(back_populates="citations")
