"""Aggregate API router mounted at /api."""

from __future__ import annotations

from fastapi import APIRouter

from vyakhya.api.routes import (
    connections,
    editor,
    pipeline,
    projects,
    prompts,
    render,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(projects.router)
api_router.include_router(editor.router)
api_router.include_router(pipeline.router)
api_router.include_router(connections.router)
api_router.include_router(prompts.router)
api_router.include_router(render.router)
