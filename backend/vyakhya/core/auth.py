"""API-key authentication for /api routes.

A single shared key (`VYAKHYA_API_KEY`, provisioned by ./setup.sh) is required
in the `X-API-Key` header. When the key is unset, auth is disabled — convenient
for local dev; a startup warning is logged.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from vyakhya.core.config import get_settings


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    settings = get_settings()
    if not settings.auth_enabled:
        return  # dev: no key configured
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
