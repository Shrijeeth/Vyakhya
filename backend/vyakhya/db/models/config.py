"""Model-configuration + install metadata: provider connections, per-role
assignments, agent prompts, and the per-install encryption salt.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from vyakhya.core.database import Base
from vyakhya.db.types import pg_enum
from vyakhya.enums import AgentId, AgentRole, ConnectionStatus, ProviderId, ProviderKind


class ProviderConnection(Base):
    __tablename__ = "provider_connections"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[ProviderId] = mapped_column(pg_enum(ProviderId, "provider_id"), nullable=False)
    # Denormalized from provider (llm vs tts) so we can filter + constrain by kind.
    kind: Mapped[ProviderKind] = mapped_column(
        pg_enum(ProviderKind, "provider_kind"), nullable=False
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    # Kind-specific tuning (LLM: temperature/max_tokens; TTS: stability/speed…).
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Encrypted secret (nonce||ciphertext); NULL for keyless providers (e.g. ollama).
    api_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    api_key_masked: Mapped[str] = mapped_column(Text, nullable=False, default="—")
    base_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ConnectionStatus] = mapped_column(
        pg_enum(ConnectionStatus, "connection_status"),
        nullable=False,
        default=ConnectionStatus.UNKNOWN,
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgentModelAssignment(Base):
    __tablename__ = "agent_model_assignments"

    role: Mapped[AgentRole] = mapped_column(pg_enum(AgentRole, "agent_role"), primary_key=True)
    connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AgentPrompt(Base):
    __tablename__ = "agent_prompts"

    id: Mapped[AgentId] = mapped_column(pg_enum(AgentId, "agent_id"), primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    default_template: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InstallMeta(Base):
    """Singleton row holding the per-install encryption salt (base64)."""

    __tablename__ = "install_meta"
    __table_args__ = (CheckConstraint("id", name="ck_install_meta_singleton"),)

    id: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=True)
    encryption_salt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
