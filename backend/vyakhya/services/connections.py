"""Provider connections + per-role model assignments."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.core.security import mask_secret
from vyakhya.db.models.config import AgentModelAssignment, ProviderConnection
from vyakhya.enums import AgentRole, ConnectionStatus
from vyakhya.schemas.config import ConnectionCreate
from vyakhya.services.crypto import get_encryptor
from vyakhya.utils import new_id, utcnow


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
        model=payload.model,
        api_key_enc=enc,
        api_key_masked=masked,
        base_url=payload.base_url,
        status=ConnectionStatus.UNKNOWN,
    )
    session.add(conn)
    await session.flush()
    return conn


async def remove_connection(session: AsyncSession, connection_id: str) -> bool:
    conn = await session.get(ProviderConnection, connection_id)
    if conn is None:
        return False
    await session.delete(conn)  # assignments nulled via ON DELETE SET NULL
    await session.flush()
    return True


async def test_connection(session: AsyncSession, connection_id: str) -> ProviderConnection | None:
    conn = await session.get(ProviderConnection, connection_id)
    if conn is None:
        return None
    # Placeholder: a real test would decrypt the key and ping the provider.
    conn.status = ConnectionStatus.OK
    conn.last_tested_at = utcnow()
    await session.flush()
    return conn


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
    "test_connection",
    "list_assignments",
    "update_assignment",
    "delete",
]
