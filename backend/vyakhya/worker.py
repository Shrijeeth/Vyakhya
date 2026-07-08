"""Procrastinate app + tasks for the worker service.

With INPROCESS_JOBS=false the API defers pipeline runs here; the compose
`worker` service executes them. Run with:

    procrastinate --app=vyakhya.worker.app worker
"""

from __future__ import annotations

import procrastinate

from vyakhya.core.config import get_settings
from vyakhya.core.logging import configure_logging, get_logger

log = get_logger(__name__)


def _dsn() -> str:
    # Procrastinate/psycopg wants a plain postgresql:// DSN (no SQLAlchemy driver).
    url = get_settings().database_url
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=_dsn()))

_opened = False


async def ensure_open() -> procrastinate.App:
    """Open the app once per process (required before deferring jobs)."""
    global _opened
    if not _opened:
        await app.open_async()
        _opened = True
    return app


@app.task(name="vyakhya.run_pipeline")
async def run_pipeline(run_id: str, project_id: str) -> None:
    """Execute a pipeline run (persists events; the API streams them from the
    event log, so no cross-process broker is needed)."""
    configure_logging()
    from vyakhya.services.pipeline import _execute

    log.info("worker executing pipeline run=%s project=%s", run_id, project_id)
    await _execute(run_id, project_id)


@app.task(name="vyakhya.run_render")
async def run_render(job_id: str) -> None:
    """Execute a render job (progress persists on the job row; the API's SSE
    stream polls it, so no cross-process broker is needed)."""
    configure_logging()
    from vyakhya.services.render import _execute_render

    log.info("worker executing render job=%s", job_id)
    await _execute_render(job_id)
