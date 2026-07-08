# Vyakhya "web" service: the TanStack Start (SSR) frontend, served by Bun.
# Build context is the REPO ROOT (needs packages/compiler):
#   docker build -f frontend/Dockerfile .

# ── Stage 1: build compiler + frontend (bun) ─────────────────────────────────
FROM oven/bun:1.3 AS build
WORKDIR /repo

# API base + key baked into the client bundle (browser → backend, cross-origin).
ARG VITE_API_KEY=""
ARG VITE_API_URL=""
ENV VITE_API_KEY=${VITE_API_KEY}
ENV VITE_API_URL=${VITE_API_URL}

COPY package.json bun.lock ./
COPY packages/compiler/package.json packages/compiler/package.json
COPY frontend/package.json frontend/package.json
COPY render/package.json render/package.json
RUN bun install --frozen-lockfile

COPY packages/compiler packages/compiler
RUN cd packages/compiler && bun run build   # frontend imports @vyakhya/compiler
COPY frontend frontend
RUN cd frontend && bun run build            # → frontend/dist (SSR server + client)

# ── Stage 2: runtime (bun serves the SSR fetch handler) ──────────────────────
FROM oven/bun:1.3 AS runtime
WORKDIR /repo
COPY --from=build /repo/node_modules ./node_modules
COPY --from=build /repo/package.json ./package.json
COPY --from=build /repo/packages/compiler ./packages/compiler
COPY --from=build /repo/frontend ./frontend

WORKDIR /repo/frontend
ENV PORT=3000
EXPOSE 3000
# Bun auto-serves the default `{ fetch }` export on $PORT. Must run with cwd =
# frontend/ so TanStack Start resolves the vite manifest + client assets
# (/assets/*) relative here — otherwise no CSS links are emitted (unstyled page).
CMD ["bun", "dist/server/server.js"]
