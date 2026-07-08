"""Small shared utilities."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime


def new_id(prefix: str) -> str:
    """Short, opaque, URL/JSON-friendly id, e.g. `p3f9a1c2b4`."""
    return f"{prefix}{secrets.token_hex(5)}"


def utcnow() -> datetime:
    return datetime.now(UTC)
