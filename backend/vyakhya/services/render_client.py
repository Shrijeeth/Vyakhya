"""Client for the Node render service — builds Scene-JSON from a project and
streams the service's SSE render progress.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from vyakhya.core.config import get_settings
from vyakhya.core.database import get_sessionmaker
from vyakhya.services.editor import get_editor_project


async def build_scene_document(project_id: str) -> dict[str, Any] | None:
    """Assemble the Scene-JSON document the render service compiles."""
    sm = get_sessionmaker()
    async with sm() as session:
        project = await get_editor_project(session, project_id)
        if project is None:
            return None
        scenes = [
            {
                "id": s.id,
                "index": s.position,
                "narration": s.narration,
                "visualType": s.visual_type.value,
                "params": s.params or {},
                "captionStyle": s.caption_style.value,
                "transition": s.transition.value,
                "durationMs": "auto" if s.duration_ms is None else s.duration_ms,
                "citations": [
                    {"id": c.id, "label": c.label, "sourceSpan": c.source_span} for c in s.citations
                ],
            }
            for s in project.scenes
        ]
        return {
            "id": project.id,
            "title": project.title,
            "aspectRatio": project.aspect_ratio.value,
            "scenes": scenes,
        }


async def capture_scene_screenshots(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-scene PNG screenshots from the render service (base64 in 'png').
    Raises on any failure — callers degrade to a text-only design review."""
    settings = get_settings()
    url = f"{settings.render_service_url}/screenshot"
    headers = {"X-API-Key": settings.render_api_key} if settings.render_api_key else {}
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(url, json={"doc": doc}, headers=headers)
        resp.raise_for_status()
        shots = resp.json().get("shots")
        return shots if isinstance(shots, list) else []


async def stream_render_service(
    doc: dict[str, Any], settings_dict: dict[str, Any]
) -> AsyncIterator[dict[str, Any]]:
    """POST to the render service and yield its SSE progress events."""
    settings = get_settings()
    url = f"{settings.render_service_url}/render"
    headers = {"X-API-Key": settings.render_api_key} if settings.render_api_key else {}
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST", url, json={"doc": doc, "settings": settings_dict}, headers=headers
        ) as resp:
            resp.raise_for_status()
            buffer = ""
            async for chunk in resp.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    for line in frame.splitlines():
                        if line.startswith("data:"):
                            yield json.loads(line[5:].strip())
