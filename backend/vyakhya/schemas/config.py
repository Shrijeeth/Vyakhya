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
