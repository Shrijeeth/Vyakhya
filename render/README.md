# services/render — Vyakhya render service

Node · TypeScript · **@hyperframes/producer**.

Takes Scene-JSON and produces MP4:
1. `@vyakhya/compiler` → HyperFrames HTML
2. `runHyperframeLint(html)` — **gate**: reject bad/non-seek-safe HTML before a costly render
3. `createRenderJob()` → `executeRenderJob()` → MP4
4. upload to MinIO/S3 · progress + status via Postgres `LISTEN/NOTIFY`

HTTP API: `POST /render`, `POST /lint`, `GET /health`. Scales via replicas (Pattern A). Uses `getCompositionDuration()` for `durationMs: "auto"` resolution.

## Dev

```bash
pnpm install
pnpm --filter @vyakhya/render dev
```

> Scaffold placeholder — Fastify app + producer wiring land here next.
