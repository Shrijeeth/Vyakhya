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
# Optionally install the Agno agent runtime (real pipeline). Off by default to
# keep the image lean; enable with: --build-arg INSTALL_AGENTS=1
ARG INSTALL_AGENTS=0
RUN if [ "$INSTALL_AGENTS" = "1" ]; then uv sync --frozen --no-dev --extra agents; \
    else uv sync --frozen --no-dev; fi

# HyperFrames agent skills (loaded as Agno LocalSkills when USE_AGNO=1).
COPY skills/ /app/skills/
ENV SKILLS_DIR=/app/skills

EXPOSE 8000
# Apply migrations, then serve. (Worker command is overridden in compose.)
CMD ["sh", "-c", "alembic upgrade head && uvicorn vyakhya.main:app --host 0.0.0.0 --port 8000"]
