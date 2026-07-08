# Vyakhya "studio" image: the FastAPI backend (API only). Also run as the
# Procrastinate worker (compose overrides the command). The frontend is a
# separate `web` service (see frontend/Dockerfile).

FROM python:3.13-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

# Backend deps + source (context is the repo root; backend lives in backend/).
COPY backend/ ./
RUN uv sync --frozen --no-dev

EXPOSE 8000
# Apply migrations, then serve. (Worker command is overridden in compose.)
CMD ["sh", "-c", "alembic upgrade head && uvicorn vyakhya.main:app --host 0.0.0.0 --port 8000"]
