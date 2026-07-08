"""Provides the configured Encryptor, backed by the per-install salt in the DB."""

from __future__ import annotations

import base64

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.core.config import get_settings
from vyakhya.core.security import Encryptor, new_salt
from vyakhya.db.models.config import InstallMeta


async def _get_or_create_salt(session: AsyncSession) -> bytes:
    row = await session.get(InstallMeta, True)
    if row is None:
        salt = new_salt()
        row = InstallMeta(id=True, encryption_salt=base64.b64encode(salt).decode())
        session.add(row)
        await session.flush()
        return salt
    return base64.b64decode(row.encryption_salt)


async def get_encryptor(session: AsyncSession) -> Encryptor:
    salt = await _get_or_create_salt(session)
    return Encryptor(get_settings().encryption_key, salt)


# Convenience for callers that only need the singleton to exist.
async def ensure_install_meta(session: AsyncSession) -> None:
    await _get_or_create_salt(session)


__all__ = ["get_encryptor", "ensure_install_meta", "select"]
