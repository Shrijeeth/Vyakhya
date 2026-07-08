# render — Vyakhya render service

Node · TypeScript · **Fastify** · **@vyakhya/compiler**.

Takes Scene-JSON and produces a video:

1. `@vyakhya/compiler` → HyperFrames HTML
2. `runHyperframeLint(html)` — **gate**: reject bad / non-seek-safe HTML before a costly render
3. render via the engine → progress → output URL

## HTTP API

| Method | Path      | Body                | Returns                        |
| ------ | --------- | ------------------- | ------------------------------ |
| GET    | `/health` | —                   | `{ status, engine }` (open)    |
| POST   | `/lint`   | `{ doc }`           | `{ ok, errors, warnings }`     |
| POST   | `/render` | `{ doc, settings }` | SSE stream of render progress  |

`/lint` and `/render` require the `X-API-Key` header when `RENDER_API_KEY` is
set (the backend sends it). Scales via replicas.

## Render engine

`RenderEngine` is a seam. `SimulatedRenderEngine` (default, `RENDER_ENGINE=simulated`)
streams progress with no Chrome/FFmpeg — used in dev, CI, and until the real
engine is wired. `HyperframesRenderEngine` (`RENDER_ENGINE=hyperframes`) is where
`@hyperframes/producer` (headless Chrome + FFmpeg → MP4 → MinIO/S3) drops in
behind the same async-generator contract.

## Config (env)

`RENDER_PORT` · `RENDER_HOST` · `RENDER_ENGINE` · `RENDER_API_KEY` ·
`RENDER_SAMPLE_URL`.

## Dev

```bash
bun run dev        # tsx watch (needs @vyakhya/compiler built: bun --cwd packages/compiler run build)
bun run build      # tsc → dist/
bun run typecheck
bun run test       # vitest
```
