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
# node:22 (not bun): the hyperframes CLI requires Node ≥22 and spawns Chrome +
# FFmpeg for real MP4 renders.
FROM node:22-bookworm-slim AS runtime
WORKDIR /repo

# FFmpeg + Playwright's Chromium build. Chrome-for-Testing has no linux-arm64
# build and Debian's chromium package SIGTRAPs inside containers on Apple
# Silicon; Playwright's Chromium is built to run in containers on both arches.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g playwright@1 \
    && playwright install --with-deps chromium \
    && ln -s "$(find /root/.cache/ms-playwright -type f -name chrome -path '*chrome-linux*' | head -1)" /usr/local/bin/pw-chromium
# Chromium runs as root inside the container → its sandbox refuses to start.
# Wrap the binary so every launch (hyperframes/puppeteer) gets the flags.
RUN printf '#!/bin/sh\nexec /usr/local/bin/pw-chromium --no-sandbox --disable-dev-shm-usage --disable-gpu "$@"\n' \
    > /usr/local/bin/chromium-nosandbox && chmod +x /usr/local/bin/chromium-nosandbox
ENV HYPERFRAMES_BROWSER_PATH=/usr/local/bin/chromium-nosandbox

COPY --from=build /repo/node_modules ./node_modules
COPY --from=build /repo/package.json ./package.json
COPY --from=build /repo/packages/compiler ./packages/compiler
COPY --from=build /repo/render ./render

ENV RENDER_PORT=8080
EXPOSE 8080
CMD ["node", "/repo/render/dist/server.js"]
