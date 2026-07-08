"""Pipeline runs, per-agent state, event log, and verifier flags."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from vyakhya.core.database import Base
from vyakhya.db.types import pg_enum
from vyakhya.enums import AgentId, AgentStatus, VerifierLevel


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[AgentStatus] = mapped_column(
        pg_enum(AgentStatus, "agent_status"), nullable=False, default=AgentStatus.QUEUED
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    procrastinate_job_id: Mapped[int | None] = mapped_column(BigInteger)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentNodeState(Base):
    __tablename__ = "agent_node_states"
    __table_args__ = (UniqueConstraint("run_id", "agent", name="uq_agent_node"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent: Mapped[AgentId] = mapped_column(pg_enum(AgentId, "agent_id"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        pg_enum(AgentStatus, "agent_status"), nullable=False, default=AgentStatus.QUEUED
    )
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PipelineEvent(Base):
    __tablename__ = "pipeline_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    agent: Mapped[AgentId | None] = mapped_column(pg_enum(AgentId, "agent_id"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VerifierFlag(Base):
    __tablename__ = "verifier_flags"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="SET NULL"))
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    source_span: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[VerifierLevel] = mapped_column(
        pg_enum(VerifierLevel, "verifier_level"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
