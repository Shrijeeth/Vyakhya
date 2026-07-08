# backend — Vyakhya Studio backend (brains)

Python · FastAPI · **Agno** (Teams + Workflows) · **Procrastinate** (Postgres async jobs). The **API** of the Studio app; the UI runs as a separate SSR `web` service (cross-origin, gated by `VYAKHYA_API_KEY` + CORS).

Responsibilities:
- Parse PDF → run the multi-agent pipeline (ingest → comprehend → plan → script → visualize → narrate → **verify** → assemble).
- Emit **Scene-JSON** (Agno `output_schema` = Pydantic models — the single contract). **Never touches HTML.**
- Model Config: store provider keys encrypted at rest (AES-256-GCM via `VYAKHYA_ENCRYPTION_KEY`).
- REST + SSE for the UI, gated by an `X-API-Key` shared key; enqueue render via the `render/` service.
- Agno **Skills** (`LocalSkills` → `../skills/hyperframes/`) power the design-time Block-Author agent.

## Stack

FastAPI · SQLAlchemy 2.0 async (asyncpg) · Alembic · Pydantic v2 / pydantic-settings ·
Procrastinate (Postgres jobs) · `cryptography` (AES-256-GCM). Agno is an optional
extra (`uv sync --extra agents`) so the core API installs fast.

## Layout

```text
vyakhya/
  core/         config · database (async engine/session) · security (key encryption) ·
                events (pub/sub → SSE) · logging
  db/
    models/     SQLAlchemy models mirroring docs/db-schema.md
    migrations/ Alembic env + versions
  enums.py      domain enums = single source for models, schemas, and DB ENUM types
  schemas/      Pydantic DTOs (camelCase wire ⇄ snake_case) matching docs/api.md
  services/     business logic — projects · editor · pipeline · connections · prompts ·
                render · crypto (encryptor + per-install salt) · mappers
  agents/       Scene-JSON schema · PipelineExecutor seam · SimulatedPipelineExecutor +
                AgnoPipelineExecutor (real crew) · model_factory (ProviderId → Agno model) ·
                skills (HyperFrames LocalSkills for the visual-designer agent)
  api/routes/   health · projects · editor · pipeline (SSE) · connections · prompts · render (SSE)
  seed.py       default prompts / render settings / install salt (on startup)
  main.py       app factory · lifespan (seed) · CORS · serve FE build
```

The wire contract is [`../docs/api.md`](../docs/api.md); the schema is
[`../docs/db-schema.md`](../docs/db-schema.md). The agent pipeline and render are
**simulated** behind clean executor seams (`agents/pipeline.py`,
`services/render.py`) — the real Agno crew and Node `render/` calls drop in there
without touching routes or services.

## Dev

```bash
uv sync                                        # create .venv + install from uv.lock
uv run alembic upgrade head                    # apply migrations (needs Postgres)
uv run uvicorn vyakhya.main:app --reload       # API on http://localhost:8000, docs at /docs
uv run procrastinate worker                    # background worker (production job path)
```

Env comes from the repo-root `.env` (see `.env.example`); `DATABASE_URL` and
`VYAKHYA_ENCRYPTION_KEY` are the two that matter. Create a migration after model
changes with `uv run alembic revision --autogenerate -m "…"`.

## Tests

Pure unit tests (no DB) covering encryption, DTO mapping, schema (camelCase)
serialization, the simulated pipeline executor, preview compile, and config.

```bash
uv run pytest -q
```

## Quality

```bash
uv run ruff check vyakhya && uv run ruff format vyakhya
```
