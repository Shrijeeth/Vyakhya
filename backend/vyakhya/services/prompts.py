"""Agent prompt templates: list, save, reset-to-default."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.db.models.config import AgentPrompt
from vyakhya.enums import AgentId


async def list_prompts(session: AsyncSession) -> list[AgentPrompt]:
    result = await session.execute(select(AgentPrompt).order_by(AgentPrompt.id))
    return list(result.scalars().all())


async def save_prompt(
    session: AsyncSession, prompt_id: AgentId, template: str
) -> AgentPrompt | None:
    prompt = await session.get(AgentPrompt, prompt_id)
    if prompt is None:
        return None
    prompt.template = template
    await session.flush()
    return prompt


async def reset_prompt(session: AsyncSession, prompt_id: AgentId) -> AgentPrompt | None:
    prompt = await session.get(AgentPrompt, prompt_id)
    if prompt is None:
        return None
    prompt.template = prompt.default_template
    await session.flush()
    return prompt
