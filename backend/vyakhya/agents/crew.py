"""Builds the pipeline's four Agno agents from the Model Config connections.

- idea (planner role)            — document + brief → detailed video idea
- scene_creator (scriptwriter)   — video idea → scene descriptions, one at
                                   a time, each seeing the previous scene
- designer (visual_designer)     — scene descriptions + HyperFrames skills
                                   → the actual frames
- reviewer (verifier role)       — screenshots + descriptions + document →
                                   issues routed to scene/design level
                                   (must be vision-capable)

Every agent's output is JSON via the ``parser`` role's model. Unassigned
roles fall back to the visual designer's connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from vyakhya.agents.model_factory import build_llm_model
from vyakhya.agents.prompt_registry import get_prompt
from vyakhya.agents.schemas import GenDocument, ReviewReport, SceneSpec, VideoIdea
from vyakhya.agents.skills import get_designer_skill_text
from vyakhya.core.logging import get_logger
from vyakhya.db.models.config import AgentModelAssignment, ProviderConnection
from vyakhya.enums import ProviderKind
from vyakhya.services.crypto import get_encryptor

log = get_logger(__name__)


@dataclass
class PipelineAgents:
    idea: Any
    scene_creator: Any
    designer: Any
    reviewer: Any


async def _connection_for(session: Any, role: str) -> tuple[ProviderConnection, str] | None:
    """The LLM connection assigned to ``role`` in Model Config (or None)."""
    assignment = await session.get(AgentModelAssignment, role)
    if assignment is None or not assignment.connection_id:
        return None
    conn = await session.get(ProviderConnection, assignment.connection_id)
    if conn is None or conn.kind != ProviderKind.LLM:
        return None
    key = ""
    if conn.api_key_enc is not None:
        key = (await get_encryptor(session)).decrypt(conn.api_key_enc)
    return conn, key


async def resolve_main_connection(session: Any) -> tuple[ProviderConnection, str] | None:
    """The visual designer's connection, falling back to any LLM connection."""
    resolved = await _connection_for(session, "visual_designer")
    if resolved is not None:
        return resolved
    result = await session.execute(
        select(ProviderConnection)
        .where(ProviderConnection.kind == ProviderKind.LLM)
        .order_by(ProviderConnection.created_at)
    )
    conn = result.scalars().first()
    if conn is None:
        return None
    key = ""
    if conn.api_key_enc is not None:
        key = (await get_encryptor(session)).decrypt(conn.api_key_enc)
    return conn, key


async def build_agents(session: Any, length_note: str) -> PipelineAgents | None:
    """Build the crew from the Model Config assignments.

    Returns None when no LLM connection exists at all."""
    from agno.agent import Agent

    main = await resolve_main_connection(session)
    if main is None:
        return None
    conns = {
        "idea": await _connection_for(session, "planner") or main,
        "scene_creator": await _connection_for(session, "scriptwriter") or main,
        "designer": main,
        "reviewer": await _connection_for(session, "verifier") or main,
        "parser": await _connection_for(session, "parser") or main,
    }

    def model(role: str) -> Any:
        conn, key = conns[role]
        log.info("%s model: %s/%s", role, conn.provider.value, conn.model)
        return build_llm_model(conn.provider, conn.model, key, conn.base_url, conn.settings)

    return PipelineAgents(
        idea=Agent(
            name="Video Idea",
            model=model("idea"),
            instructions=[get_prompt("idea-system")],
            output_schema=VideoIdea,
            parser_model=model("parser"),
            markdown=False,
        ),
        scene_creator=Agent(
            name="Scene Creator",
            model=model("scene_creator"),
            instructions=[get_prompt("scene-creator-system")],
            output_schema=SceneSpec,
            parser_model=model("parser"),
            markdown=False,
        ),
        designer=Agent(
            name="Visual Designer",
            model=model("designer"),
            # HyperFrames guides are INLINED (tool-based skill loading costs
            # 4-5 extra round trips per call on slow endpoints). Only the
            # designer needs them.
            instructions=[get_prompt("designer-system"), length_note, get_designer_skill_text()],
            output_schema=GenDocument,
            parser_model=model("parser"),
            markdown=False,
        ),
        reviewer=Agent(
            name="Reviewer",
            model=model("reviewer"),
            instructions=[get_prompt("reviewer-system")],
            output_schema=ReviewReport,
            parser_model=model("parser"),
            markdown=False,
        ),
    )
