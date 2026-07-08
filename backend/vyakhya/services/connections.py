"""Provider connections + per-role model assignments."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.core.logging import get_logger
from vyakhya.core.security import mask_secret
from vyakhya.db.models.config import AgentModelAssignment, ProviderConnection
from vyakhya.enums import AgentRole, ConnectionStatus, provider_kind
from vyakhya.schemas.config import ConnectionCreate, ConnectionTest
from vyakhya.services.crypto import get_encryptor
from vyakhya.services.probe import ProbeResult, probe_provider
from vyakhya.utils import new_id, utcnow

log = get_logger(__name__)


async def list_connections(session: AsyncSession) -> list[ProviderConnection]:
    result = await session.execute(
        select(ProviderConnection).order_by(ProviderConnection.created_at)
    )
    return list(result.scalars().all())


async def create_connection(session: AsyncSession, payload: ConnectionCreate) -> ProviderConnection:
    api_key = (payload.api_key or "").strip()
    enc = None
    masked = "—"
    if api_key:
        encryptor = await get_encryptor(session)
        enc = encryptor.encrypt(api_key)
        masked = mask_secret(api_key)

    conn = ProviderConnection(
        id=new_id("c"),
        provider=payload.provider,
        kind=provider_kind(payload.provider),  # derived, never trusted from client
        model=payload.model,
        api_key_enc=enc,
        api_key_masked=masked,
        base_url=payload.base_url,
        settings=payload.settings or {},
        status=ConnectionStatus.UNKNOWN,
    )
    session.add(conn)
    await session.flush()
    log.info(
        "connection created id=%s provider=%s kind=%s model=%s keyless=%s",
        conn.id,
        conn.provider.value,
        conn.kind.value,
        conn.model,
        enc is None,
    )
    return conn


async def remove_connection(session: AsyncSession, connection_id: str) -> bool:
    conn = await session.get(ProviderConnection, connection_id)
    if conn is None:
        log.warning("connection remove: not found id=%s", connection_id)
        return False
    await session.delete(conn)  # assignments nulled via ON DELETE SET NULL
    await session.flush()
    log.info("connection removed id=%s provider=%s", connection_id, conn.provider.value)
    return True


async def probe_draft(session: AsyncSession, payload: ConnectionTest) -> ProbeResult:
    """Probe an unsaved connection (add-connection form) — nothing persisted."""
    log.info("connection probe (draft) provider=%s model=%s", payload.provider.value, payload.model)
    return await probe_provider(
        payload.provider, payload.model, (payload.api_key or "").strip(), payload.base_url
    )


async def test_connection(
    session: AsyncSession, connection_id: str
) -> tuple[ProviderConnection, ProbeResult] | None:
    """Probe a saved connection: decrypt its key, ping the provider, persist status."""
    conn = await session.get(ProviderConnection, connection_id)
    if conn is None:
        log.warning("connection test: not found id=%s", connection_id)
        return None
    api_key = ""
    if conn.api_key_enc is not None:
        encryptor = await get_encryptor(session)
        api_key = encryptor.decrypt(conn.api_key_enc)
    result = await probe_provider(conn.provider, conn.model, api_key, conn.base_url)
    conn.status = ConnectionStatus.OK if result.success else ConnectionStatus.ERROR
    conn.last_tested_at = utcnow()
    await session.flush()
    log.info(
        "connection tested id=%s provider=%s success=%s ms=%s",
        conn.id,
        conn.provider.value,
        result.success,
        result.latency_ms,
    )
    return conn, result


async def list_assignments(session: AsyncSession) -> list[AgentModelAssignment]:
    result = await session.execute(select(AgentModelAssignment))
    existing = {a.role: a for a in result.scalars().all()}
    # Ensure a row exists for every role (nullable connection).
    for role in AgentRole:
        if role not in existing:
            row = AgentModelAssignment(role=role, connection_id=None)
            session.add(row)
            existing[role] = row
    await session.flush()
    return [existing[role] for role in AgentRole]


async def update_assignment(
    session: AsyncSession, role: AgentRole, connection_id: str | None
) -> list[AgentModelAssignment]:
    row = await session.get(AgentModelAssignment, role)
    if row is None:
        row = AgentModelAssignment(role=role, connection_id=connection_id)
        session.add(row)
    else:
        row.connection_id = connection_id
    await session.flush()
    return await list_assignments(session)


__all__ = [
    "list_connections",
    "create_connection",
    "remove_connection",
    "probe_draft",
    "test_connection",
    "list_assignments",
    "update_assignment",
    "delete",
]
