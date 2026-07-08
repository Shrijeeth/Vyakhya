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


@app.task(name="vyakhya.run_pipeline")
async def run_pipeline(run_id: str, project_id: str) -> None:
    """Execute a pipeline run (persists events; the API streams them from the
    event log, so no cross-process broker is needed)."""
    configure_logging()
    from vyakhya.services.pipeline import _execute

    log.info("worker executing pipeline run=%s project=%s", run_id, project_id)
    await _execute(run_id, project_id)
