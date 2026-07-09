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
    ORBIT_3D = "orbit.3d"
    # Agent-authored scene: the designer writes the stage HTML/CSS itself
    # (HyperFrames-safe subset) instead of picking a canned layout.
    CUSTOM_HTML = "custom.html"


class CaptionStyle(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    BOLD = "bold"


class SceneTransition(StrEnum):
    CUT = "cut"
    FADE = "fade"
    SLIDE = "slide"
    WIPE = "wipe"


class ProviderKind(StrEnum):
    """A connection is either an LLM (agents) or a TTS (narrator) provider."""

    LLM = "llm"
    TTS = "tts"


class ProviderId(StrEnum):
    # LLM providers (agent reasoning + vision).
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROQ = "groq"
    OLLAMA = "ollama"  # keyless (local)
    # TTS providers (narration).
    HYPERFRAMES = "hyperframes"  # keyless (built-in)
    ELEVENLABS = "elevenlabs"
    DEEPGRAM = "deepgram"
    # Bring-your-own OpenAI-compatible endpoints (model + base URL entered
    # by the user): /chat/completions for LLM, /audio/speech for TTS.
    CUSTOM = "custom"
    CUSTOM_TTS = "custom_tts"


# The kind is a property of the provider — a single provider_connections table
# stores both; `kind` is persisted (denormalized) for cheap filtering + a DB
# CHECK that the narrator role only binds a TTS connection.
_TTS_PROVIDERS = frozenset(
    {ProviderId.HYPERFRAMES, ProviderId.ELEVENLABS, ProviderId.DEEPGRAM, ProviderId.CUSTOM_TTS}
)
# Keyless providers run locally / built-in and need no API key.
KEYLESS_PROVIDERS = frozenset({ProviderId.OLLAMA, ProviderId.HYPERFRAMES})


def provider_kind(provider: ProviderId) -> ProviderKind:
    return ProviderKind.TTS if provider in _TTS_PROVIDERS else ProviderKind.LLM


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
    SCENES = "scenes"
    PROGRESS = "progress"
    ERROR = "error"
    DONE = "done"
