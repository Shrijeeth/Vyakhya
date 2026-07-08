# frontend — Vyakhya Studio UI

**TanStack Start** (React · Router · Query) · TypeScript · Tailwind v4 · shadcn/ui. The Studio frontend (served by `backend/` in production). Migrated from the Lovable "Vyakhya Studio" design.

**Screens:** Projects · New Project (PDF upload) · Pipeline view (React Flow DAG of the agent run + live logs + verifier flags) · **Editor** (scene list/timeline · live HyperFrames **HTML** preview · scene inspector) · Model Config (provider + model + key per agent role) · Agent Prompts (Monaco) · Render Settings (schema-driven) + MP4 export.

Talks to `backend/` over REST + WebSocket/SSE via the typed `src/services/` layer. Currently backed by in-memory mocks (`src/services/mock-data.ts`) with simulated latency — swap in real calls in `src/services/api.ts` with no screen changes. Wire contract: [`../docs/api.md`](../docs/api.md).

## Stack

- **TanStack Start** — file-based routing (`src/routes/`), SSR, `@tanstack/react-query`
- **Tailwind v4** + **shadcn/ui** (Radix) — `src/components/ui/`
- **zustand** editor store — `src/store/editor-store.ts`
- **React Flow** (`@xyflow/react`) pipeline DAG · **Monaco** prompt editor · **Recharts** dataviz
- **bun** package manager (part of the repo-root workspace)

## Dev

Run from the repo root (single bun workspace):

```bash
bun install                 # from repo root
bun --cwd frontend dev      # http://localhost:5173
```

Or from this folder:

```bash
bun run dev       # dev server
bun run build     # client + SSR build
bun run lint      # eslint
```

## Layout

```text
src/
  routes/         file-based routes (index, dashboard, model-config,
                  render-settings, agent-prompts, projects.$projectId.editor|pipeline)
  components/     ui/ (shadcn) · layout/ · editor/ · projects/
  services/       api.ts (service layer) · types.ts (domain contract) · mock-data.ts
  store/          zustand editor store
  hooks/  lib/    utilities
  styles.css      Tailwind v4 theme (oklch design tokens)
  server.ts start.ts   TanStack Start SSR entry + error middleware
```
