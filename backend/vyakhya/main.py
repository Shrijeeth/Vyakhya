"""FastAPI application factory for Vyakhya Studio.

Run: uvicorn vyakhya.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
