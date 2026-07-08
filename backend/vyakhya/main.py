"""FastAPI application factory for Vyakhya Studio.

Run: uvicorn vyakhya.main:app --reload
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from vyakhya import __version__
from vyakhya.api.router import api_router
from vyakhya.core.config import get_settings
from vyakhya.core.database import dispose_engine, get_sessionmaker
from vyakhya.core.logging import configure_logging, get_logger
from vyakhya.seed import seed_defaults

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    if not settings.is_encryption_key_secure:
        log.warning(
            "VYAKHYA_ENCRYPTION_KEY is unset/insecure — provider keys are not safely "
            "encrypted. Run ./setup.sh to provision one for production."
        )
    if not settings.auth_enabled:
        log.warning(
            "VYAKHYA_API_KEY is unset — /api routes are UNAUTHENTICATED. Run ./setup.sh "
            "to provision one for production."
        )
    try:
        async with get_sessionmaker()() as session:
            await seed_defaults(session)
    except Exception:  # noqa: BLE001 - don't crash boot if DB is briefly unavailable
        log.exception("startup seeding skipped (database unavailable?)")
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Multi-agent engine that turns papers into detailed, editable explainer videos."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = int((time.monotonic() - started) * 1000)
            log.exception("request failed %s %s (%dms)", request.method, request.url.path, elapsed)
            raise
        elapsed = int((time.monotonic() - started) * 1000)
        log.info(
            "%s %s -> %s (%dms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(api_router)

    # The frontend is served by the separate `web` (SSR) service; this is an
    # API-only app.
    @app.get("/", tags=["health"])
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "docs": "/docs"}

    return app


app = create_app()
