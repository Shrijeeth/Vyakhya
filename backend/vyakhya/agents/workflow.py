"""The pipeline as an Agno Workflow: six named steps over one shared context.

Steps communicate through ``PipelineContext`` (not step outputs) and stream
progress to the UI via ``ctx.emit``; the workflow provides ordering and
fail-fast semantics."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from vyakhya.agents.context import PipelineContext
from vyakhya.agents.steps import assemble, design, idea, ingest, outline, review


def build_pipeline_workflow(ctx: PipelineContext) -> Any:
    from agno.workflow import OnError, Step, StepOutput, Workflow

    def as_step(name: str, fn: Callable) -> Step:
        async def executor(step_input) -> StepOutput:  # noqa: ANN001
            await fn(ctx)
            return StepOutput(content=f"{name} complete")

        executor.__name__ = name
        # fail: a step that raises (e.g. designer produced no scenes) must
        # abort the run — soft failures are handled inside the steps.
        return Step(name=name, executor=executor, on_error=OnError.fail)

    return Workflow(
        name="vyakhya-pipeline",
        steps=[
            as_step("ingest", ingest.run),
            as_step("idea", idea.run),
            as_step("outline", outline.run),
            as_step("design", design.run),
            as_step("review", review.run),
            as_step("assemble", assemble.run),
        ],
        telemetry=False,
    )
