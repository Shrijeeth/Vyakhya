"""Agent prompt templates: list, save, reset-to-default."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vyakhya.core.logging import get_logger
from vyakhya.db.models.config import AgentPrompt
from vyakhya.enums import AgentId

log = get_logger(__name__)


async def list_prompts(session: AsyncSession) -> list[AgentPrompt]:
    result = await session.execute(select(AgentPrompt).order_by(AgentPrompt.id))
    return list(result.scalars().all())


async def save_prompt(
    session: AsyncSession, prompt_id: AgentId, template: str
) -> AgentPrompt | None:
    prompt = await session.get(AgentPrompt, prompt_id)
    if prompt is None:
        log.warning("save_prompt: not found id=%s", prompt_id)
        return None
    prompt.template = template
    await session.flush()
    log.info("prompt saved id=%s len=%d", prompt_id.value, len(template))
    return prompt


async def reset_prompt(session: AsyncSession, prompt_id: AgentId) -> AgentPrompt | None:
    prompt = await session.get(AgentPrompt, prompt_id)
    if prompt is None:
        log.warning("reset_prompt: not found id=%s", prompt_id)
        return None
    prompt.template = prompt.default_template
    await session.flush()
    log.info("prompt reset id=%s", prompt_id.value)
    return prompt
