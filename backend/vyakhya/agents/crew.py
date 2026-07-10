"""Builds the pipeline's Agno agents from the Model Config connections.

One place decides which model powers which agent:
- each ``AgentRole`` can be assigned a connection in Model Config;
- unassigned roles fall back to the visual designer's connection;
- the ``parser`` role is the structured-output converter every agent uses
  (assign a fast model — its whole job is emitting schema JSON).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from vyakhya.agents.model_factory import build_llm_model
from vyakhya.agents.prompt_registry import get_prompt
from vyakhya.agents.schemas import (
    DesignReviewReport,
    GenDocument,
    ResearchNotes,
    StoryPlan,
    VerifierReport,
)
from vyakhya.agents.skills import get_designer_skill_text
from vyakhya.core.logging import get_logger
from vyakhya.db.models.config import AgentModelAssignment, ProviderConnection
from vyakhya.enums import ProviderKind
from vyakhya.services.crypto import get_encryptor

log = get_logger(__name__)


@dataclass
class PipelineAgents:
    designer: Any
    planner: Any
    verifier: Any
    reviewer: Any
    researcher: Any


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


def _research_tools() -> list[Any]:
    """Web tools for the researcher, skipping any whose deps are missing."""
    tools: list[Any] = []
    try:
        from agno.tools.duckduckgo import DuckDuckGoTools

        tools.append(DuckDuckGoTools())
    except Exception as exc:  # noqa: BLE001 - optional dep
        log.warning("DuckDuckGo tools unavailable: %s", exc)
    try:
        from agno.tools.wikipedia import WikipediaTools

        tools.append(WikipediaTools())
    except Exception as exc:  # noqa: BLE001 - optional dep
        log.warning("Wikipedia tools unavailable: %s", exc)
    return tools


async def build_agents(session: Any, length_note: str) -> PipelineAgents | None:
    """Build every pipeline agent from the Model Config assignments.

    Returns None when no LLM connection exists at all."""
    from agno.agent import Agent

    main = await resolve_main_connection(session)
    if main is None:
        return None
    conns = {"main": main}
    for role in ("comprehension", "planner", "verifier", "parser"):
        conns[role] = await _connection_for(session, role) or main

    def model_for(role: str) -> Any:
        conn, key = conns.get(role) or main
        log.info("%s model: %s/%s", role, conn.provider.value, conn.model)
        return build_llm_model(conn.provider, conn.model, key, conn.base_url, conn.settings)

    def parser() -> Any:
        conn, key = conns["parser"]
        return build_llm_model(conn.provider, conn.model, key, conn.base_url, conn.settings)

    return PipelineAgents(
        designer=Agent(
            name="Visual Designer",
            model=model_for("main"),
            # HyperFrames guides are INLINED (tool-based skill loading costs
            # 4-5 extra round trips per call on slow endpoints).
            instructions=[get_prompt("designer-system"), length_note, get_designer_skill_text()],
            output_schema=GenDocument,
            parser_model=parser(),
            markdown=False,
        ),
        planner=Agent(
            name="Planner",
            model=model_for("planner"),
            instructions=[get_prompt("planner-system")],
            output_schema=StoryPlan,
            parser_model=parser(),
            markdown=False,
        ),
        verifier=Agent(
            name="Verifier",
            model=model_for("verifier"),
            instructions=[get_prompt("verifier-system")],
            output_schema=VerifierReport,
            parser_model=parser(),
            markdown=False,
        ),
        reviewer=Agent(
            name="Design Reviewer",
            # Shares the verifier role's connection (must be vision-capable).
            model=model_for("verifier"),
            instructions=[get_prompt("reviewer-system")],
            output_schema=DesignReviewReport,
            parser_model=parser(),
            markdown=False,
        ),
        researcher=Agent(
            name="Researcher",
            model=model_for("comprehension"),
            tools=_research_tools(),
            instructions=[get_prompt("researcher-system")],
            output_schema=ResearchNotes,
            parser_model=parser(),
            markdown=False,
        ),
    )
