"""Aggregate API router mounted at /api."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from vyakhya.api.routes import (
    connections,
    editor,
    pipeline,
    projects,
    prompts,
    render,
)
from vyakhya.core.auth import require_api_key

api_router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])
api_router.include_router(projects.router)
api_router.include_router(editor.router)
api_router.include_router(pipeline.router)
api_router.include_router(connections.router)
api_router.include_router(prompts.router)
api_router.include_router(render.router)
