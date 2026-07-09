"""Model-config DTOs: provider connections, assignments, agent prompts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vyakhya.enums import AgentId, AgentRole, ConnectionStatus, ProviderId, ProviderKind
from vyakhya.schemas.common import CamelModel


class ProviderConnectionOut(CamelModel):
    id: str
    provider: ProviderId
    kind: ProviderKind  # derived from provider (llm | tts)
    model: str
    api_key_masked: str
    base_url: str | None = None
    status: ConnectionStatus
    settings: dict = Field(default_factory=dict)
    last_tested_at: datetime | None = None


class ConnectionCreate(CamelModel):
    provider: ProviderId
    model: str
    api_key: str = ""
    base_url: str | None = None
    # Kind-specific tuning (LLM: temperature…; TTS: stability/speed…). `kind`
    # itself is derived from `provider` server-side — never trusted from client.
    settings: dict = Field(default_factory=dict)


class ConnectionTest(CamelModel):
    """Probe an unsaved (draft) connection from the add-connection form."""

    provider: ProviderId
    model: str
    api_key: str = ""
    base_url: str | None = None
    settings: dict = Field(default_factory=dict)


class ConnectionTestResult(CamelModel):
    success: bool
    latency_ms: int
    detail: str | None = None
    error: str | None = None
    # Canary probe (LLM): whether the system codeword / user answer appeared.
    system_honored: bool | None = None
    user_honored: bool | None = None
    response: str | None = None


class AgentModelAssignmentOut(CamelModel):
    role: AgentRole
    connection_id: str | None = None


class AssignmentUpdate(CamelModel):
    connection_id: str | None = None


class PromptVariable(CamelModel):
    name: str
    description: str


class AgentPromptOut(CamelModel):
    id: AgentId
    label: str
    template: str
    default_template: str
    variables: list[PromptVariable] = Field(default_factory=list)


class PromptUpdate(CamelModel):
    template: str


class ConnectionUpdate(CamelModel):
    """Partial update for a saved connection. ``api_key`` empty/None keeps the
    stored key; provider/kind are immutable."""

    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    settings: dict | None = None


class AgentSettingsIO(CamelModel):
    """Pipeline loop knobs (Settings → Agents)."""

    verifier_max_rounds: int = Field(default=3, ge=1, le=10)
    visual_max_rounds: int = Field(default=8, ge=1, le=20)
    visual_stall_rounds: int = Field(default=2, ge=1, le=5)
    length_fit_rounds: int = Field(default=3, ge=0, le=5)
