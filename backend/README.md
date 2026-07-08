# backend — Vyakhya Studio backend (brains)

Python · FastAPI · **Agno** (Teams + Workflows) · **Procrastinate** (Postgres async jobs). Serves the built `frontend/` in production — together they are the single **Studio** app.

Responsibilities:
- Parse PDF → run the multi-agent pipeline (ingest → comprehend → plan → script → visualize → narrate → **verify** → assemble).
- Emit **Scene-JSON** (Agno `output_schema` = Pydantic models — the single contract). **Never touches HTML.**
- Model Config: store provider keys encrypted at rest (AES-256-GCM via `VYAKHYA_ENCRYPTION_KEY`).
- REST + WebSocket/SSE for the UI; enqueue render via the `render/` service.
- Agno **Skills** (`LocalSkills` → `../skills/hyperframes/`) power the design-time Block-Author agent.
- Serve the frontend build (static) so the app ships as one container.

## Dev

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn vyakhya.main:app --reload
# worker:
procrastinate worker
```

> Scaffold placeholder — module layout, pyproject, and the Scene-JSON Pydantic models land here next.
