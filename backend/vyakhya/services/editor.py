"""Editor: load the editable timeline, persist a scene, compile a preview."""

from __future__ import annotations

from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vyakhya.db.models.project import Project, Scene, SceneCitation
from vyakhya.schemas.project import SceneIn
from vyakhya.utils import new_id


async def get_editor_project(session: AsyncSession, project_id: str) -> Project | None:
    result = await session.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.scenes).selectinload(Scene.citations))
    )
    return result.scalar_one_or_none()


async def save_scene(session: AsyncSession, project_id: str, scene_in: SceneIn) -> Scene | None:
    result = await session.execute(
        select(Scene)
        .where(Scene.id == scene_in.id, Scene.project_id == project_id)
        .options(selectinload(Scene.citations))
    )
    scene = result.scalar_one_or_none()
    if scene is None:
        return None

    scene.position = scene_in.index
    scene.narration = scene_in.narration
    scene.visual_type = scene_in.visual_type
    scene.params = scene_in.params
    scene.caption_style = scene_in.caption_style
    scene.transition = scene_in.transition
    scene.duration_ms = None if scene_in.duration_ms == "auto" else int(scene_in.duration_ms)

    # Replace citations wholesale (simple, deterministic).
    scene.citations.clear()
    for pos, c in enumerate(scene_in.citations):
        scene.citations.append(
            SceneCitation(
                id=c.id or new_id("c"),
                label=c.label,
                source_span=c.source_span,
                position=pos,
            )
        )
    await session.flush()
    return scene


def compile_scene_preview(scene: SceneIn) -> str:
    """Themed standalone HTML preview. Placeholder for the HyperFrames compiler
    (`@vyakhya/compiler`); mirrors the frontend mock output.
    """
    narration = escape(scene.narration)
    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        "html,body{margin:0;height:100%;font-family:Inter,system-ui,sans-serif;"
        "background:#faf7f0;color:#1c1e2e}"
        ".stage{display:flex;align-items:center;justify-content:center;height:100%;"
        "padding:6% 8%;box-sizing:border-box;text-align:center}"
        ".card{max-width:900px}h1{font-size:56px;line-height:1.1;margin:0 0 16px;"
        "letter-spacing:-0.02em}p{font-size:22px;line-height:1.5;color:#4a4f66;margin:0}"
        ".tag{display:inline-block;font-size:12px;letter-spacing:.14em;text-transform:uppercase;"
        "color:#4b3fbf;background:#eae7ff;padding:6px 12px;border-radius:999px;margin-bottom:20px}"
        '</style></head><body><div class="stage"><div class="card">'
        f'<div class="tag">{scene.visual_type.value}</div>'
        f"<h1>Scene {scene.index}</h1><p>{narration}</p>"
        "</div></div></body></html>"
    )
