# Vyakhya — Architecture & Frontend OSS Components

## 1. High-level shape
```
┌─────────────────────────────────────────────┐
│  Frontend (React · TanStack Start)            │
│  → Tailwind v4 + shadcn/ui + Radix            │
│  • API-key & provider settings                │
│  • Agent prompt editor                        │
│  • Pipeline (agent DAG) view                  │
│  • Scene/text editor (NOT raw HTML)           │
│  • Video preview + timeline                   │
└───────────────┬─────────────────────────────┘
                │ REST / WebSocket (job status, streaming logs)
┌───────────────▼─────────────────────────────┐
│  Backend (Python — FastAPI)                   │
│  • Multi-agent orchestrator                   │
│  • PDF parse → comprehend → plan → script     │
│    → visualize → narrate → verify → assemble  │
│  • Scene-JSON  ⇄  HyperFrames HTML compiler    │
│  • Render (HyperFrames → MP4), TTS, storage    │
│  • Encrypted key vault, proxy to LLM/TTS APIs  │
└──────────────────────────────────────────────┘
```

> The concrete REST + WebSocket/SSE wire contract between frontend and backend — endpoints, schemas, streaming event shapes — is specified in [`api.md`](api.md), derived from the frontend service layer.

## 2. The key design decision: **Scene-JSON is the source of truth, not HTML**
Users must edit **scenes and text in an editor**, never raw HTML. So the pipeline must NOT treat HTML as the editable artifact:

- Agents emit a structured **Scene Graph (JSON)** — an ordered list of scenes:
  ```jsonc
  {
    "scenes": [
      {
        "id": "s1",
        "durationMs": 6000,
        "narration": "Attention lets the model weigh every token...",
        "visual": { "type": "diagram.attention", "params": {...} },
        "captionStyle": "anchor",
        "sourceSpans": ["p3:¶2"]     // citation grounding for the verifier
      }
    ]
  }
  ```
- A backend **compiler** deterministically turns Scene-JSON → **HyperFrames HTML** for render.
- The FE editor reads/writes **Scene-JSON only**. Editing narration = editing a text field; editing a visual = form controls / presets; reordering = drag on a timeline. HTML is a compiled artifact the user never touches.
- Round-trip safe: edit JSON → recompile HTML → re-render. Deterministic, diffable, versionable (git-friendly — fits OSS ethos).

> This is also the moat vs NotebookLM: the artifact is structured and editable, not an opaque MP4.

### Compile location: **client-side (locked)**
The Scene-JSON → HyperFrames HTML compiler runs **in the browser** for instant preview (zero round-trip, offline-capable). Consequence:
- The compiler is a **shared TypeScript package** (`@vyakhya/compiler`) used in **two** places: (1) the browser editor for live preview, (2) the **Node render worker** that headless-renders the same HTML → MP4. One compiler, one output — preview == final, guaranteed.
- **Python never touches HTML.** The Python backend does agent orchestration only and emits **Scene-JSON**. Rendering is a **Node/HyperFrames** worker (HyperFrames is a JS toolchain anyway). Clean split: Python = brains (agents → Scene-JSON), TS/Node = rendering, browser = editing/preview.
- Scene-JSON is the single contract crossing all three (Python ⇄ browser ⇄ render worker) — design its schema first.

## 3. Frontend feature → OSS component map
All MIT/permissive unless noted; all compatible with the frontend stack (React · TanStack Start · Tailwind v4 · shadcn/ui).

| FE surface | Recommended OSS | License | Notes |
|-----------|-----------------|---------|-------|
| **UI kit / primitives** | **shadcn/ui** + Radix + Tailwind | MIT | Lovable's default — everything else layers on this |
| **Agent pipeline (DAG) view/edit** | **React Flow (@xyflow/react)** | MIT | Node-based canvas to show the 8-agent pipeline; click a node to configure/inspect. Alt: Rete.js |
| **Agent prompt editor** | **Monaco Editor** (`@monaco-editor/react`) or **CodeMirror 6** | MIT | Code-grade editing for prompt templates; syntax highlight, `{{variables}}`, diff view. Monaco = VS Code feel; CM6 = lighter |
| **Scene text / narration editor** | **BlockNote** (Notion-style) or **Tiptap** (headless) | BlockNote MPL-2.0 (core free for commercial; AI/export extras GPL/paid) · Tiptap MIT | BlockNote = fastest Notion-like UX out of the box; Tiptap = full control if you want a bespoke scene-block UI |
| **Timeline / scene arrangement** | **react-timeline-editor** (xzdarcy) or **Twick** SDK | MIT / OSS | Drag/trim/reorder scenes on a track. Twick is a fuller React video-editor SDK (timeline + captions + export) — heavier but more complete. Verify Twick license before adopting |
| **Editor preview (primary)** | **HyperFrames composition in an iframe**, driven by `hf-seek` | — | The editor previews **live HTML, not video** — the composition runs in the browser, scrubbed via HyperFrames' seek timeline. Instant WYSIWYG; no render step in the edit loop |
| **Final-video player (export only)** | **Vidstack** (`@vidstack/react`) or react-player | MIT | Plays/downloads the **exported MP4** (backend headless-renders HTML → MP4). Not used during editing |
| **API-key & provider settings forms** | **react-hook-form** + **zod** + shadcn form | MIT | Plain forms — the hard part is storage/security, see §4 |
| **Data fetching / job status** | **TanStack Query** + WebSocket | MIT | Poll/stream render + agent progress |
| **Client state** | **Zustand** | MIT | Lightweight editor state (selected scene, dirty flags) |
| **Auth / DB / storage / realtime** | **Supabase** | Apache-2.0 | Lovable-native. Or skip and let FastAPI + Postgres own it |

### Full-editor shortcut (optional)
If you'd rather not assemble the timeline yourself: **designcombo/react-video-editor** (OSS base; a paid "Pro" exists at reactvideoeditor.com) and **Twick** are the closest drop-in React video-editor shells. Trade-off: they assume *their* render model, while Vyakhya renders via HyperFrames — so you'd use them for the **editing UI only** and keep Scene-JSON→HyperFrames as the render path. Adopt for speed, or build a lean timeline on react-timeline-editor for tighter fit.

## 3b. Agent layer — Agno (locked)
The Python brains run on **Agno** (agno-agi, formerly Phidata; model-agnostic, high-perf multi-agent). Mapping:

| Vyakhya need | Agno primitive |
|--------------|----------------|
| The 8-step pipeline (ingest → comprehend → plan → script → visualize → narrate → verify → assemble) | **Workflow** — structured sequential/parallel/conditional steps |
| The collaborating crew within a step (e.g. planner + scriptwriter + visual designer + verifier) | **Team** — specialized agents with roles |
| **Scene-JSON as the contract** | Agent **`output_schema`** = Pydantic models → agents return validated Scene-JSON directly (no parse glue) |
| BYO-key OSS story | Agno is **model-agnostic** — swap OpenAI/Anthropic/local per user/workspace |
| Tools (PDF parse, figure extract, citation lookup) | Agno **tools** |
| Grounding / recall across a long paper | Agno **memory + knowledge** |

### Agno Skills — loading the HyperFrames skill
Agno ships a **Skills** system (based on the Anthropic Agent Skills spec): `LocalSkills` reads a directory of `SKILL.md` + `scripts/` + `references/`, lazy-loaded via injected tools (`get_skill_instructions`, `get_skill_reference`, `get_skill_script`) — no context bloat.

```python
from agno.agent import Agent
from agno.skills import Skills, LocalSkills
block_author = Agent(model=..., skills=Skills(loaders=[LocalSkills("./skills/hyperframes")]))
```

HyperFrames already ships a `SKILL.md`, so it drops in. **But where it loads matters — do NOT put HTML generation on the runtime render path** (it breaks determinism, preview==final, and "edit scenes not HTML"). Two safe placements:

1. **Block-Author agent (design-time)** ⭐ — loads the HyperFrames skill and **authors a reusable `visual.type` block** (HyperFrames component + params schema + editor control) that is committed into `@vyakhya/compiler`'s **registry**. The LLM writes HTML **once per block type** → reviewed/tested → **deterministic forever**. This automates the community registry-contribution flow.
2. **`custom.freeform` escape hatch (runtime, optional)** — an assembler agent generates bespoke HyperFrames HTML for a one-off the registry can't express. Output is **frozen into the scene** (content-hash cached) so re-render stays deterministic; editing that scene = regenerate. Quarantined from the deterministic path; used sparingly.

> Net: the HyperFrames skill powers **block authoring**, not per-video rendering. Main path stays compiler-deterministic (§7); the skill expands the *registry* the compiler dispatches to.

**Deployment:** plain Agno (Agents/Teams/Workflows) **embedded inside FastAPI** — same for self-host and cloud. **No AgentOS.** Multi-tenancy, auth, RBAC, and job isolation are handled by our own FastAPI + Postgres/Supabase layer, not Agno's runtime. Keeps the dependency surface small and the self-host story simple.

> Design consequence: define the Scene-JSON Pydantic schema **once** in Python (Agno `output_schema`), then mirror it as the TS type in `@vyakhya/compiler`. Keep them in sync (generate TS from Pydantic, e.g. via JSON Schema) so the contract can't drift.

## 4. Model configuration UI + key storage (self-host, no vault)

Provider keys are entered in the FE; the **encryption key is env-only** (set by the setup wizard, §4b). **No passphrase in the UI at all.**

### Model Configuration UI
- Add a **provider connection**: pick **provider** (OpenAI / Anthropic / ElevenLabs / local Ollama…), pick **model**, paste **API key**, optional base URL.
- Assign providers/models **per agent role** (e.g. comprehension → a strong model, captions → a cheap one) — surfaces the model-agnostic Agno layer.
- Test-connection button; mask keys in UI (`sk-...abcd`); rotate/revoke.
- The UI **never** handles the encryption key — only provider keys.

### Key storage — env-provisioned encryption key
- A single **`VYAKHYA_ENCRYPTION_KEY`** lives in **env** (`.env`), provisioned by the **setup wizard** (§4b). Derive the symmetric key from it (**Argon2id/scrypt + per-install salt** stored in DB).
- Provider API keys are encrypted with **authenticated encryption** (AES-256-GCM or libsodium `secretbox`, per-key nonce); only **ciphertext** is stored in Postgres. No plaintext keys at rest.
- **Auto-unlock from env on start** — no manual step, headless-friendly. Standard self-host pattern (cf. Django `SECRET_KEY`, n8n `N8N_ENCRYPTION_KEY`). **Fixes the "forgot passphrase = lockout" problem** — the key is in `.env`, backed up with infra.
- **Restart does NOT re-encrypt.** Salt is persisted; same env key + same salt → same derived key → existing ciphertext decrypts unchanged. Ciphertext changes **only** on an explicit **key-rotation** action (decrypt-with-old → encrypt-with-new, one transaction; replace salt).
- **Never** send keys to the browser or store in `localStorage`; all provider calls are **proxied server-side**.

### Honest threat model (state it in docs)
- Protects the **common leak vector** — DB dumps/backups contain only ciphertext.
- `.env` is now *the* secret: an attacker with **both** the DB *and* `.env` gets everything → `chmod 600 .env`, never commit it, back it up **separately** from DB dumps.
- Does **not** protect a **compromised running server** (key is in memory while running) — acceptable for single-tenant self-host, strictly better than plaintext keys. A real KMS/vault is the future cloud upgrade, not now.
- **Recovery:** lose `VYAKHYA_ENCRYPTION_KEY` (and its backup) → stored provider keys are unrecoverable by design → operator re-enters provider keys in the UI. No backdoor.

## 4b. Setup & onboarding — scripted terminal wizard
Self-host install is a **scripted terminal experience** (installer/first-run wizard), not manual file editing:
- One command bootstraps: checks Docker, **generates a strong random `VYAKHYA_ENCRYPTION_KEY`** (or accepts an operator-provided one), writes `.env` (DB creds, storage, key), runs migrations, and `docker compose up`.
- Interactive prompts for essentials; sensible defaults for the rest. Prints next steps (URL, how to add provider keys in the Model Config UI).
- Idempotent + re-runnable (upgrade path); a `--headless`/flags mode for CI/servers.
- Ships with the compose file so `git clone → ./setup.sh → open browser` is the whole install.

## 5. Frontend origin & integration notes
- The Studio UI was designed in **Lovable** and has since been **migrated into `frontend/` as a standalone TanStack Start app** (React · Router · Query · Tailwind v4 · shadcn/ui) — no Lovable/Supabase runtime dependency. All components above drop in cleanly.
- Lovable produced the **shell** (settings, layout, forms, pipeline view). The heavier pieces (Monaco, timeline, preview) are hand-wired in `frontend/src/components/`.
- Keep the **Python agent backend separate** (FastAPI). Python owns orchestration, compilation, and rendering; the frontend is a pure client over a REST/WS contract — see [`api.md`](api.md).

## 6. Recommended default stack (copy-paste decision)
- **FE:** React · **TanStack Start** (Router + Query) · Tailwind v4 + shadcn/ui · React Flow · Monaco · Zustand · react-hook-form + zod · **bun**
- **BE (brains):** Python + FastAPI · agent orchestration via **Agno** (Teams + Workflows) · emits **Scene-JSON** · Procrastinate (Postgres-backed async task queue) for jobs · Postgres (or Supabase). *Never touches HTML.*
- **Compiler:** `@vyakhya/compiler` — shared **TypeScript** package (Scene-JSON → HyperFrames HTML), imported by both the browser editor and the render worker.
- **Render worker:** **Node** + HyperFrames (`@hyperframes/producer`) — compiles Scene-JSON→HTML then headless-renders → MP4. Separate from Python (see §8).
- **Contract:** **Scene-JSON schema** is the interface across Python ⇄ browser ⇄ render worker — design it first.

## 7. Jobs & deployment (single docker-compose)

### Task queue: Procrastinate (Postgres-backed, async)
Heavy work — the Agno agent pipeline and the HyperFrames render — runs as **Procrastinate** jobs, not inline in the request. Why Procrastinate over Celery/RQ/APScheduler:
- **Async-native**, fits FastAPI.
- **Horizontally scalable** — many worker processes/nodes on one Postgres; jobs pulled with `SELECT ... FOR UPDATE SKIP LOCKED` (no double-processing, no external lock manager). `LISTEN/NOTIFY` for low-latency pickup.
- **Vertically scalable** — each worker runs multiple async tasks concurrently.
- **No Redis / no extra broker** — uses the Postgres you already run. Fewer services = better OSS self-host adoption.
- Bottleneck is compute (GPU/LLM), not queue throughput — job count is few-but-heavy, well within Postgres.
- **APScheduler** is kept only for *periodic chores* (cleanup of old renders, retry sweeps, usage rollups) — a scheduler, not the job queue.
- Progress streams to the FE via **WebSocket/SSE**; multi-node fan-out uses Postgres **`LISTEN/NOTIFY`** (still no Redis).

### Compose services (default = Postgres-only)
```yaml
services:
  web:            # FastAPI — API, auth, WS/SSE, enqueues jobs. Embeds Agno (no AgentOS).
  worker:         # Procrastinate worker — runs Agno pipeline, produces Scene-JSON. Scale: replicas.
  render:         # Node + HyperFrames — Scene-JSON → HTML → MP4 (headless). Scale: replicas.
  postgres:       # DB + Procrastinate queue + LISTEN/NOTIFY pub/sub + cache tables.
  frontend:       # React/Vite build (or served via CDN / static host in prod).
  # storage: object store for PDFs + rendered MP4s (S3/MinIO; MinIO container for self-host).
```
- **Scale out** by bumping `worker` / `render` replica counts — all coordinate through Postgres.
- **Redis is NOT here.** Add only on a measured need, as an optional profile:
```yaml
  redis:
    profiles: ["redis"]   # opt-in: hot cache / heavy rate-limiting / multi-node WS at scale
```
- **MinIO** (S3-compatible) recommended for self-host object storage so PDFs/MP4s don't bloat Postgres; managed cloud uses real S3.

> Net self-host footprint: `web + worker + render + postgres (+ minio)`. One data service, no broker. Clean `docker compose up`.

## 8. Calling HyperFrames from the backend

HyperFrames (HeyGen, open-source, `npm i hyperframes`) is a **Node** toolchain with two invocation surfaces:

| Surface | What it is | When |
|---------|-----------|------|
| **CLI** `npx hyperframes render` | headless Chrome frame-seek + FFmpeg encode | Local dev, MVP, quick automation |
| **`@hyperframes/producer`** | Node API: build render-job config → execute → MP4/WebM, with progress hooks | **Backend service — preferred.** Structured progress + errors, no arg-string parsing |

**Use `@hyperframes/producer` in the render script, not raw CLI**, so render progress feeds the WS/SSE stream and errors are structured.

**Python ↔ Node boundary** (Procrastinate is Python; HyperFrames is Node) — two patterns:

**Pattern A — decoupled Node render service (recommended for scale)**
```
Python worker → Scene-JSON → HTTP POST /render → Node render service
  Node: @vyakhya/compiler (JSON→HTML) + @hyperframes/producer (HTML→MP4)
      → upload MinIO/S3 → status via Postgres LISTEN/NOTIFY → FE progress
```
- Node service scales on its own replicas; Python image stays lean (no Chrome/FFmpeg).
- Clean seam; the two runtimes never share a process.

**Pattern B — subprocess (simplest MVP)**
- One worker image (Python + Node + Chrome + FFmpeg). Python Procrastinate task calls `node render.mjs <sceneDoc>` via `subprocess`, which runs compiler + producer.
- Fewer services, but fatter image and coupled scaling.

**Decision (locked): Pattern A from MVP.** The docker-compose already has a dedicated `render` container (§7), so the decoupled Node service costs almost nothing extra — just a thin HTTP endpoint — while keeping the Python image lean (no Chrome/FFmpeg) and avoiding a later B→A migration. Pattern B (subprocess) is only a fallback if you ever want to collapse to a single image.

**HyperFrames is called programmatically (not via CLI shelling).** The full CLI flow — lint, validate, render — is exposed as Node APIs; the CLI just wraps them:
- **`@hyperframes/core`** — types, parsers, **linter**, runtime.
- **`@hyperframes/producer`** — `prepareHyperframeLintBody()` + `runHyperframeLint()` (lint/verify; also a `POST /lint` endpoint), `createRenderJob()` → `executeRenderJob()` (render, with fps/quality/format/workers/GPU), and `getCompositionDuration()` (**use for `durationMs: "auto"` resolution**).

**MVP render service shape:**
```
Node service (Fastify/Express):
  POST /render { sceneDocId }  -> 202 + jobId
  → load Scene-JSON → @vyakhya/compiler (JSON→HTML)
  → runHyperframeLint(HTML)                 // GATE: reject bad HTML before a costly render
  → createRenderJob() → executeRenderJob()  // HTML→MP4 (producer)
  → upload to MinIO/S3 → emit progress + final status via Postgres LISTEN/NOTIFY
  POST /lint  { html | sceneDocId }          // reuse lint standalone (Block-Author / custom.freeform)
  GET  /health
```
- The **lint gate** matters for the two LLM-authored HTML paths — the **Block-Author agent** and **`custom.freeform`** scenes: lint *before* render to catch malformed / non-seek-safe HTML cheaply, and run the same lint in CI when new registry blocks are added.
- Python worker enqueues the render step, calls `POST /render`, and streams progress to the FE from the same `LISTEN/NOTIFY` channel. Scale = bump `render` replicas.

## 9. All HyperFrames params are FE-tunable (schema-driven)

Requirement: **every HyperFrames parameter is adjustable from the FE**, not hardcoded. Do it with a **typed config surfaced as a schema-driven form**, so adding a param can never silently skip the UI.

### Two param buckets (different editors)
- **Composition params** (content) — `aspectRatio`, `theme`/palette, `font`, `voice`, `bgm`, `captionStyle`. Already live in **Scene-JSON** `meta`/`theme`/`audio`; edited in the scene editor; consumed by `@vyakhya/compiler`.
- **RenderConfig** (output/encode) — `fps`, `resolution` (w×h), `quality`/CRF, `format` (mp4/webm), `codec`, `gpu` on/off, `workers` (concurrency), `audioMix` levels, `frameRangePreview`. Edited in a **Render Settings panel**; passed straight to `createRenderJob()`.

### Schema-driven, anti-drift (same pattern as Scene-JSON)
- Define **`RenderConfig`** once as a **Pydantic** model → generate the **TS type + JSON Schema** in `@vyakhya/compiler` (or a shared `@vyakhya/config`).
- FE renders the settings form **from the JSON Schema** (react-hook-form + zod, or a JSON-Schema form). **New param in the model → control appears automatically.** This is what makes "all params tunable" true and self-maintaining.
- The render service wrapper maps `RenderConfig` 1:1 onto `createRenderJob()` options — one adapter, kept in sync by the shared type.

### Layering (defaults → overrides)
1. **Self-host global defaults** — env / config file (uncapped).
2. **Workspace/project defaults** — stored in Postgres, edited in FE.
3. **Per-render overrides** — one-off tweaks at render time.
Resolution order: per-render → project → global.

### Governance
- **Scope now = self-host only → uncapped.** Their hardware, their rules; no plan limits required.
- Keep an **optional** env-config clamp (max resolution/fps/duration/concurrency) so an operator *can* bound their box, but it defaults off.
- Expose "advanced" params (workers/GPU/codec) behind a disclosure so casual users see only resolution/format/quality.
- **Future (cloud):** the same clamp code becomes plan-capped per workspace — a clean open-core seam, but **out of scope for now.**

