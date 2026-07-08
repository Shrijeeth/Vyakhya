# Vyakhya render service. Build context is the REPO ROOT (it needs
# packages/compiler), so build with: docker build -f render/Dockerfile .

# ── Stage 1: build compiler + render (bun) ───────────────────────────────────
FROM oven/bun:1.3 AS build
WORKDIR /repo

COPY package.json bun.lock ./
COPY packages/compiler/package.json packages/compiler/package.json
COPY frontend/package.json frontend/package.json
COPY render/package.json render/package.json
RUN bun install --frozen-lockfile

COPY packages/compiler packages/compiler
RUN cd packages/compiler && bun run build   # render imports @vyakhya/compiler
COPY render render
RUN cd render && bun run build              # → render/dist

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM oven/bun:1.3 AS runtime
WORKDIR /repo
COPY --from=build /repo/node_modules ./node_modules
COPY --from=build /repo/package.json ./package.json
COPY --from=build /repo/packages/compiler ./packages/compiler
COPY --from=build /repo/render ./render

ENV RENDER_PORT=8080
EXPOSE 8080
CMD ["bun", "/repo/render/dist/server.js"]
