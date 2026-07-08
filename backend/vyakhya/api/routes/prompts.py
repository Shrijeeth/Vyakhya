"""Agent prompt endpoints (docs/api.md → Agent prompts)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from vyakhya.api.deps import SessionDep
from vyakhya.enums import AgentId
from vyakhya.schemas.config import AgentPromptOut, PromptUpdate
from vyakhya.services import prompts as svc

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=list[AgentPromptOut])
async def list_prompts(session: SessionDep) -> list[AgentPromptOut]:
    return [AgentPromptOut.model_validate(p) for p in await svc.list_prompts(session)]


@router.put("/{prompt_id}", response_model=AgentPromptOut)
async def save_prompt(
    prompt_id: AgentId, payload: PromptUpdate, session: SessionDep
) -> AgentPromptOut:
    prompt = await svc.save_prompt(session, prompt_id, payload.template)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return AgentPromptOut.model_validate(prompt)


@router.post("/{prompt_id}/reset", response_model=AgentPromptOut)
async def reset_prompt(prompt_id: AgentId, session: SessionDep) -> AgentPromptOut:
    prompt = await svc.reset_prompt(session, prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return AgentPromptOut.model_validate(prompt)
