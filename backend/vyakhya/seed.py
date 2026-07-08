"""Idempotent seeding of default rows: agent prompts, render settings, and the
per-install encryption salt. Runs on startup.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.core.logging import get_logger
from vyakhya.db.models.config import AgentPrompt
from vyakhya.db.models.render import RenderSettings
from vyakhya.enums import AgentId
from vyakhya.services.crypto import ensure_install_meta

log = get_logger(__name__)

_DEFAULT_PROMPTS: list[dict] = [
    {
        "id": AgentId.COMPREHENSION,
        "label": "Comprehension",
        "template": (
            "You are a research analyst. Read the paper below and produce a structured "
            "comprehension:\n- Core claim\n- Method\n- Key results\n- Limitations\n\nPaper:\n"
            "{{paper_text}}"
        ),
        "variables": [
            {"name": "paper_text", "description": "Full parsed text of the paper"},
            {"name": "audience", "description": "Layperson | Student | Expert"},
        ],
    },
    {
        "id": AgentId.PLANNER,
        "label": "Planner",
        "template": (
            "Given the comprehension, plan a {{target_length}} explainer for a {{audience}} "
            "audience. Output an ordered list of scene beats.\n\nComprehension:\n{{comprehension}}"
        ),
        "variables": [
            {"name": "comprehension", "description": "Output of the Comprehension agent"},
            {"name": "target_length", "description": "Target video length hint"},
            {"name": "audience", "description": "Layperson | Student | Expert"},
        ],
    },
    {
        "id": AgentId.SCRIPTWRITER,
        "label": "Scriptwriter",
        "template": (
            "Write the narration for each scene beat. Voice: {{voice_style}}.\n\nBeats:\n{{beats}}"
        ),
        "variables": [
            {"name": "beats", "description": "Scene beats from Planner"},
            {"name": "voice_style", "description": "Narrative voice guidance"},
        ],
    },
    {
        "id": AgentId.VISUAL_DESIGNER,
        "label": "Visual Designer",
        "template": (
            "For each scene, choose a visual type from the library and produce its parameters. "
            "Prefer figures cited by the paper when available.\n\nScenes:\n{{scenes}}\n\nFigures:\n"
            "{{figures}}"
        ),
        "variables": [
            {"name": "scenes", "description": "Scene list with narration"},
            {"name": "figures", "description": "Extracted figures and tables"},
        ],
    },
    {
        "id": AgentId.NARRATOR,
        "label": "Narrator (TTS)",
        "template": (
            "Voice: {{voice_id}}\nSpeed: {{speed}}\nStability: {{stability}}\n\n"
            "Render the following narration as audio, one file per scene."
        ),
        "variables": [
            {"name": "voice_id", "description": "TTS voice identifier"},
            {"name": "speed", "description": "Speaking rate multiplier"},
            {"name": "stability", "description": "Voice stability 0..1"},
        ],
    },
    {
        "id": AgentId.VERIFIER,
        "label": "Verifier",
        "template": (
            "For every factual claim in the narration, locate its source span in the paper. "
            "Flag any claim not supported.\n\nNarration:\n{{narration}}\n\nPaper:\n{{paper_text}}"
        ),
        "variables": [
            {"name": "narration", "description": "Full narration text"},
            {"name": "paper_text", "description": "Full parsed paper text"},
        ],
    },
]


async def seed_defaults(session: AsyncSession) -> None:
    await ensure_install_meta(session)

    # Render settings singleton.
    if await session.get(RenderSettings, True) is None:
        session.add(RenderSettings(id=True))

    # Agent prompts (only if empty).
    count = await session.scalar(select(func.count()).select_from(AgentPrompt))
    if not count:
        for p in _DEFAULT_PROMPTS:
            session.add(
                AgentPrompt(
                    id=p["id"],
                    label=p["label"],
                    template=p["template"],
                    default_template=p["template"],
                    variables=p["variables"],
                )
            )
        log.info("seeded %d default agent prompts", len(_DEFAULT_PROMPTS))

    await session.commit()
