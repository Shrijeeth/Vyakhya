"""Unit tests for settings normalization."""

from __future__ import annotations

from vyakhya.core.config import Settings


def test_sqlalchemy_url_adds_asyncpg_driver():
    s = Settings(DATABASE_URL="postgresql://u:p@host:5432/db")
    assert s.sqlalchemy_url == "postgresql+asyncpg://u:p@host:5432/db"


def test_sqlalchemy_url_keeps_explicit_driver():
    s = Settings(DATABASE_URL="postgresql+asyncpg://u:p@host:5432/db")
    assert s.sqlalchemy_url == "postgresql+asyncpg://u:p@host:5432/db"


def test_encryption_key_security_flag():
    assert Settings(VYAKHYA_ENCRYPTION_KEY="dev-insecure-key").is_encryption_key_secure is False
    assert Settings(VYAKHYA_ENCRYPTION_KEY="a-real-strong-key").is_encryption_key_secure is True
