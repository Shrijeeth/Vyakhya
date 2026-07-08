# frontend — Vyakhya Studio UI

React + Vite + TypeScript + Tailwind + shadcn/ui. The Studio frontend (served by `backend/` in production).

**Screens:** Projects · New Project (PDF upload) · Pipeline view (React Flow DAG of the agent run + live logs + verifier flags) · **Editor** (scene list/timeline · live HyperFrames **HTML** preview · scene inspector) · Model Config (provider + model + key per agent role) · Agent Prompts (Monaco) · Render Settings (schema-driven) + MP4 export.

Talks to `backend/` over REST + WebSocket/SSE via a typed `src/services/` layer.

> Scaffold target for the Lovable build — see [`../docs/lovable-prompts.md`](../docs/lovable-prompts.md) (Prompt 1, the app UI). Frontend only; no auth/billing/cloud. The landing site is a separate Lovable project, not in this repo.

## Dev

```bash
pnpm install
pnpm --filter @vyakhya/frontend dev
```
