"""Render settings (singleton) and render jobs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from vyakhya.core.database import Base
from vyakhya.db.types import pg_enum
from vyakhya.enums import RenderStatus, VideoCodec, VideoFormat


class RenderSettings(Base):
    """Single-row table (global render defaults)."""

    __tablename__ = "render_settings"
    __table_args__ = (
        CheckConstraint("id", name="ck_render_settings_singleton"),
        CheckConstraint("fps IN (24, 30, 60)", name="ck_render_fps"),
        CheckConstraint("quality BETWEEN 0 AND 100", name="ck_render_quality"),
    )

    id: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=True)
    fps: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=30)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=1920)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=1080)
    quality: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=82)
    format: Mapped[VideoFormat] = mapped_column(
        pg_enum(VideoFormat, "video_format"), nullable=False, default=VideoFormat.MP4
    )
    codec: Mapped[VideoCodec] = mapped_column(
        pg_enum(VideoCodec, "video_codec"), nullable=False, default=VideoCodec.H264
    )
    gpu: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    workers: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=4)
    audio_master_db: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    audio_narration_db: Mapped[float] = mapped_column(Float, nullable=False, default=-2.0)
    audio_music_db: Mapped[float] = mapped_column(Float, nullable=False, default=-14.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RenderJob(Base):
    __tablename__ = "render_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[RenderStatus] = mapped_column(
        pg_enum(RenderStatus, "render_status"), nullable=False, default=RenderStatus.QUEUED
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_url: Mapped[str | None] = mapped_column(Text)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
