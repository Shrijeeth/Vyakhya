"""Render DTOs (docs/api.md → Render)."""

from __future__ import annotations

from typing import Literal

from vyakhya.enums import RenderStatus, VideoCodec, VideoFormat
from vyakhya.schemas.common import CamelModel


class RenderSettingsIO(CamelModel):
    fps: Literal[24, 30, 60] = 30
    width: int = 1920
    height: int = 1080
    quality: int = 82
    format: VideoFormat = VideoFormat.MP4
    codec: VideoCodec = VideoCodec.H264
    gpu: bool = True
    workers: int = 4
    audio_master_db: float = 0.0
    audio_narration_db: float = -2.0
    audio_music_db: float = -14.0


class RenderJobOut(CamelModel):
    id: str
    status: RenderStatus
    progress: float
    output_url: str | None = None
