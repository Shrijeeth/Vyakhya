"""Unit tests for the API-key dependency."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from vyakhya.core import auth


class _FakeSettings:
    def __init__(self, key: str) -> None:
        self.api_key = key

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)


async def test_auth_disabled_allows_any(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _FakeSettings(""))
    assert await auth.require_api_key(None) is None


async def test_missing_key_rejected(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _FakeSettings("secret"))
    with pytest.raises(HTTPException) as exc:
        await auth.require_api_key(None)
    assert exc.value.status_code == 401


async def test_wrong_key_rejected(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _FakeSettings("secret"))
    with pytest.raises(HTTPException):
        await auth.require_api_key("nope")


async def test_valid_key_accepted(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _FakeSettings("secret"))
    assert await auth.require_api_key("secret") is None
