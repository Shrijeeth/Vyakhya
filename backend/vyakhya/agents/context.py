"""Shared state and event plumbing for the pipeline workflow steps.

``PipelineContext`` carries the project inputs, the agents, the tunables
from Settings, and the mutable artifacts (plan → scenes → payload) that
flow between steps. Steps talk to the UI through ``ctx.log/flag/scenes``
and wrap themselves in ``ctx.stage(...)`` so every stage in the fixed
AGENT_SEQUENCE gets its running/done status and progress tick.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from vyakhya.agents.events import AGENT_SEQUENCE, pipeline_event
from vyakhya.agents.schemas import GenDocument
from vyakhya.core.logging import get_logger
from vyakhya.enums import AgentId, AgentStatus, PipelineEventType

log = get_logger(__name__)

# Scenes per designer call: scene JSON is heavy (~1.5k output tokens of
# html+css per scene); more per completion risks truncation.
SCENE_BATCH = 6
# Final cut must land within this fraction of the requested length.
DURATION_TOLERANCE = 0.15


@dataclass
class Tunables:
    """Agent-settings knobs (Settings → Agents tab)."""

    review_rounds: int = 8
    review_stall_rounds: int = 2
    length_fit_rounds: int = 3


@dataclass
class PipelineContext:
    project_id: str
    title: str
    audience: str
    language: str
    target_min: int
    tts_enabled: bool
    aspect: str
    user_prompt: str
    paper_text: str
    figures: list[dict]
    paper_file_url: str | None
    tunables: Tunables
    agents: Any  # PipelineAgents
    emit: Callable[[dict], None]

    # Mutable artifacts, filled in by the steps.
    idea: str = ""
    outline: list[str] = field(default_factory=list)  # scene descriptions, in order
    doc: GenDocument | None = None
    scenes_payload: list[dict] = field(default_factory=list)
    _stages_done: int = 0

    # ── Event helpers ──────────────────────────────────────────────────────────
    def log(self, agent_id: AgentId, message: str) -> None:
        self.emit(pipeline_event(PipelineEventType.LOG, message, agent_id))

    def flag(self, agent_id: AgentId, payload: dict) -> None:
        self.emit(pipeline_event(PipelineEventType.FLAG, payload, agent_id))

    def scenes(self, agent_id: AgentId) -> None:
        self.emit(pipeline_event(PipelineEventType.SCENES, self.scenes_payload, agent_id))

    def status(self, agent_id: AgentId, value: AgentStatus) -> None:
        self.emit(pipeline_event(PipelineEventType.STATUS, value.value, agent_id))

    @property
    def target_ms(self) -> int:
        return max(1, self.target_min) * 60_000

    @property
    def figure_map(self) -> dict[str, str]:
        return {f["id"]: f["url"] for f in self.figures if f.get("url")}

    @property
    def brief(self) -> str:
        """The user's creative brief, prepended to EVERY designer prompt."""
        if not self.user_prompt:
            return ""
        return (
            "USER BRIEF — HIGHEST PRIORITY, overrides all defaults. Follow its "
            f"story structure, tone, and style in every scene:\n{self.user_prompt}\n\n"
        )

    @asynccontextmanager
    async def stage(self, agent_id: AgentId, label: str):  # noqa: ANN201
        """running status + working log on entry; done status + progress on exit."""
        self.status(agent_id, AgentStatus.RUNNING)
        self.log(agent_id, f"[{label}] working…")
        try:
            yield
        except Exception:
            self.status(agent_id, AgentStatus.ERROR)
            raise
        self.status(agent_id, AgentStatus.DONE)
        self._stages_done += 1
        self.emit(
            pipeline_event(
                PipelineEventType.PROGRESS, round(self._stages_done / len(AGENT_SEQUENCE), 3)
            )
        )

    # ── Model-call helper ──────────────────────────────────────────────────────
    async def call(
        self,
        agent: Any,
        prompt: str,
        *,
        images: list | None = None,
        heartbeat: tuple[AgentId, str] | None = None,
        attempts: int = 2,
        backoff_s: int = 90,
    ) -> Any:
        """One agent call with heartbeat events, outage backoff, and the real
        failure surfaced (Agno swallows provider errors into an errored run).

        Returns the run's content; raises RuntimeError with the cause after
        all attempts fail."""
        last_error: Exception | None = None
        for attempt in range(attempts):
            task = asyncio.ensure_future(agent.arun(input=prompt, images=images, stream=False))
            started, waited = time.monotonic(), 0
            while True:
                done, _ = await asyncio.wait({task}, timeout=60)
                if done:
                    break
                waited += 60
                if heartbeat is not None:
                    agent_id, label = heartbeat
                    self.log(agent_id, f"[{label}] still generating… ({waited}s)")
            try:
                res = task.result()
            except Exception as exc:  # noqa: BLE001 - retry with backoff
                last_error = exc
                log.warning("%s attempt %d failed: %s", agent.name, attempt + 1, exc)
                if attempt < attempts - 1:
                    await asyncio.sleep(backoff_s)
                continue
            log.info("%s call took %.1fs", agent.name, time.monotonic() - started)
            content = res.content if res else None
            status = str(getattr(getattr(res, "status", None), "value", "") or "").lower()
            if content is None and (res is None or status == "error"):
                last_error = RuntimeError("model call failed (see worker logs)")
                if attempt < attempts - 1:
                    await asyncio.sleep(backoff_s)
                continue
            return content
        raise RuntimeError(str(last_error) if last_error else "model call failed")
