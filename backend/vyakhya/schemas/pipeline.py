"""Pipeline DTOs (docs/api.md → Pipeline streaming)."""

from __future__ import annotations

from typing import Any

from vyakhya.enums import AgentId, PipelineEventType, VerifierLevel
from vyakhya.schemas.common import CamelModel


class AgentSequenceItem(CamelModel):
    id: AgentId
    label: str


class VerifierFlagOut(CamelModel):
    id: str
    claim: str
    source_span: str
    level: VerifierLevel
    note: str | None = None


class PipelineEventOut(CamelModel):
    type: PipelineEventType
    agent_id: AgentId | None = None
    payload: Any = None
