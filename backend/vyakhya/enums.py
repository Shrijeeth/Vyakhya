"""Domain enums — the single Python source for the value sets shared by the
SQLAlchemy models, Pydantic schemas, and the DB `ENUM` types. Values mirror the
TS union types in `frontend/src/services/types.ts` exactly (wire compatibility).
"""

from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class AudienceLevel(StrEnum):
    LAYPERSON = "layperson"
    STUDENT = "student"
    EXPERT = "expert"


class AspectRatio(StrEnum):
    WIDE = "16:9"
    VERTICAL = "9:16"
    SQUARE = "1:1"


class AgentId(StrEnum):
    INGESTOR = "ingestor"
    COMPREHENSION = "comprehension"
    PLANNER = "planner"
    SCRIPTWRITER = "scriptwriter"
    VISUAL_DESIGNER = "visual_designer"
    NARRATOR = "narrator"
    VERIFIER = "verifier"
    ASSEMBLER = "assembler"


class AgentStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class AgentRole(StrEnum):
    """Subset of AgentId that gets a model assigned (no ingestor/assembler)."""

    COMPREHENSION = "comprehension"
    PLANNER = "planner"
    SCRIPTWRITER = "scriptwriter"
    VISUAL_DESIGNER = "visual_designer"
    NARRATOR = "narrator"
    VERIFIER = "verifier"


class VisualType(StrEnum):
    TITLE_CARD = "title.card"
    BULLET_REVEAL = "bullet.reveal"
    FIGURE_CALLOUT = "figure.callout"
    EQUATION_BUILD = "equation.build"
    DATAVIZ_BAR = "dataviz.bar"
    DIAGRAM_ATTENTION = "diagram.attention"
    COMPARISON_SPLIT = "comparison.split"
    KINETIC_TYPE = "kinetic.type"


class CaptionStyle(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    BOLD = "bold"


class SceneTransition(StrEnum):
    CUT = "cut"
    FADE = "fade"
    SLIDE = "slide"
    WIPE = "wipe"


class ProviderId(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ELEVENLABS = "elevenlabs"
    OLLAMA = "ollama"
    GEMINI = "gemini"
    GROQ = "groq"


class ConnectionStatus(StrEnum):
    UNKNOWN = "unknown"
    OK = "ok"
    ERROR = "error"


class VerifierLevel(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class RenderStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class VideoFormat(StrEnum):
    MP4 = "mp4"
    WEBM = "webm"


class VideoCodec(StrEnum):
    H264 = "h264"
    H265 = "h265"
    VP9 = "vp9"
    AV1 = "av1"


class PipelineEventType(StrEnum):
    STATUS = "status"
    LOG = "log"
    FLAG = "flag"
    PROGRESS = "progress"
    DONE = "done"
