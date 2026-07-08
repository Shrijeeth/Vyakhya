# Vyakhya API Contract

Backend contract derived from the frontend service layer
([`frontend/src/services/api.ts`](../frontend/src/services/api.ts) and
[`types.ts`](../frontend/src/services/types.ts)). The frontend currently runs
against in-memory mocks with simulated latency; every function below is a seam
where a real REST / WebSocket / SSE call plugs in. Screens import these
functions unchanged, so **matching these shapes exactly means the UI works with
zero frontend edits**.

- Base URL: `/api` (suggested). All bodies JSON unless noted.
- IDs are opaque strings. Timestamps are ISO-8601 UTC strings.
- Two long-running flows (pipeline, render) are **streams** — served as **SSE**.

## Authentication

All `/api/*` routes require a shared API key in the `X-API-Key` header when
`VYAKHYA_API_KEY` is set (provisioned by `./setup.sh`; the frontend build embeds
it as `VITE_API_KEY`). Missing/invalid → `401`. `/health` and `/docs` are open.
When the key is unset, auth is disabled (local dev) and a startup warning logs.

The streaming endpoints are **Server-Sent Events** over `fetch` (so the auth
header can be sent — `EventSource` cannot set headers). Each event is one
`data: <json>\n\n` frame matching the shapes below.

---

## Enums

| Type | Values |
|------|--------|
| `ProjectStatus` | `draft` \| `generating` \| `ready` \| `failed` |
| `AudienceLevel` | `layperson` \| `student` \| `expert` |
| `AspectRatio` | `16:9` \| `9:16` \| `1:1` |
| `AgentId` | `ingestor` \| `comprehension` \| `planner` \| `scriptwriter` \| `visual_designer` \| `narrator` \| `verifier` \| `assembler` |
| `AgentStatus` | `queued` \| `running` \| `done` \| `error` |
| `AgentRole` | `comprehension` \| `planner` \| `scriptwriter` \| `visual_designer` \| `narrator` \| `verifier` |
| `VisualType` | `title.card` \| `bullet.reveal` \| `figure.callout` \| `equation.build` \| `dataviz.bar` \| `diagram.attention` \| `comparison.split` \| `kinetic.type` |
| `ProviderId` | LLM: `openai` \| `anthropic` \| `gemini` \| `groq` \| `ollama` — TTS: `hyperframes` \| `elevenlabs` \| `deepgram` |
| `ProviderKind` | `llm` (agents) \| `tts` (narrator) |
| `VerifierFlag.level` | `pass` \| `warn` \| `fail` |
| `Scene.captionStyle` | `none` \| `minimal` \| `bold` |
| `Scene.transition` | `cut` \| `fade` \| `slide` \| `wipe` |
| `RenderJob.status` | `queued` \| `running` \| `done` \| `error` |

---

## Projects

### `GET /api/projects`
List all projects. → `Project[]`

```jsonc
// Project
{
  "id": "p1",
  "title": "Attention Is All You Need — Explained",
  "sourcePaper": "Vaswani et al., 2017",
  "thumbnail": null,                 // optional URL
  "status": "ready",
  "durationMs": 342000,              // 0 until a render exists
  "updatedAt": "2026-07-05T10:24:00Z",
  "audience": "student",
  "aspectRatio": "16:9",
  "language": "en"
}
```

### `GET /api/projects/:id`
→ `Project` (404 if missing).

### `POST /api/projects`
Create a project from an uploaded document. **multipart/form-data** (carries the PDF).

| Field | Type | Notes |
|-------|------|-------|
| `file` | file (PDF) | the source document |
| `audience` | `AudienceLevel` | |
| `aspectRatio` | `AspectRatio` | |
| `language` | string | e.g. `en` |
| `targetLengthMin` | number | desired video length (minutes) |

→ `Project` with `status: "generating"`, `durationMs: 0`. Title defaults to the
filename minus `.pdf`. Creating a project is expected to kick off the pipeline
(see below).

---

## Pipeline (streaming)

Drives the agent-crew progress screen. The frontend subscribes to a stream and
receives `PipelineEvent`s until a terminal `done`.

### `GET /api/projects/:id/pipeline/stream` — WebSocket **or** SSE
Emits `PipelineEvent`:

```jsonc
// PipelineEvent
{
  "type": "status" | "log" | "flag" | "progress" | "done",
  "agentId": "comprehension",  // present for status/log
  "payload": <depends on type>
}
```

| `type` | `payload` |
|--------|-----------|
| `status` | `AgentStatus` string (`"running"`, `"done"`, `"error"`) for `agentId` |
| `log` | log line string for `agentId` |
| `progress` | number `0..1` (overall) |
| `flag` | a `VerifierFlag` object (emitted by the `verifier` stage) |
| `done` | `null` — pipeline finished |

Agent sequence (order the UI expects): `ingestor → comprehension → planner →
scriptwriter → visual_designer → narrator → verifier → assembler`.

```jsonc
// VerifierFlag
{
  "id": "vf2",
  "claim": "Transformer trained in 12 hours on 8 P100 GPUs.",
  "sourceSpan": "§5.1, p. 7",
  "level": "warn",
  "note": "Paper reports 12h for base model; large model took 3.5 days." // optional
}
```

### `GET /api/projects/:id/verifier-flags`
Fetch the latest verifier flags without streaming. → `VerifierFlag[]`

---

## Editor

### `GET /api/projects/:id/editor`
Full editable timeline. → `EditorProject`

```jsonc
// EditorProject
{
  "id": "p1",
  "title": "Attention Is All You Need — Explained",
  "aspectRatio": "16:9",
  "totalDurationMs": 342000,
  "scenes": [ /* Scene[] */ ]
}

// Scene
{
  "id": "s1",
  "index": 1,                        // 1-based, contiguous
  "narration": "In 2017, a team at Google…",
  "visualType": "title.card",
  "params": { "title": "…", "subtitle": "…" },  // shape depends on visualType, see below
  "captionStyle": "minimal",
  "transition": "fade",
  "durationMs": 6000,                // number, or the string "auto"
  "citations": [
    { "id": "c1", "label": "[1]", "sourceSpan": "§1.1, p. 3" }
  ]
}
```

### `PUT /api/projects/:id/scenes/:sceneId`
Persist a single edited scene. Body: `Scene`. → the saved `Scene`.

### `POST /api/projects/:id/scenes/:sceneId/preview`
Compile a scene to a standalone HTML preview string (the HyperFrames renderer in
production). Body: `Scene`. → `{ "html": "<!doctype html>…" }` (or `text/html`).

#### `Scene.params` by `visualType`

| visualType | params |
|------------|--------|
| `title.card` | `{ title: string, subtitle: string }` |
| `bullet.reveal` | `{ bullets: string[] }` |
| `figure.callout` | `{ caption: string, figureRef?: string }` |
| `equation.build` | `{ latex: string }` |
| `dataviz.bar` | `{ series: { label: string, value: number }[] }` |
| `diagram.attention` | `{ tokens: string[] }` |
| `comparison.split` | `{ left: string, right: string }` |
| `kinetic.type` | `{ text: string }` |

---

## Model configuration

Provider connections + per-agent-role model assignments. Providers are one of two
**kinds**: **LLM** providers (`openai`, `anthropic`, `gemini`, `groq`, `ollama`)
drive the reasoning/vision agents; **TTS** providers (`hyperframes`, `elevenlabs`,
`deepgram`) drive the narrator. The `narrator` role only accepts a TTS connection;
every other role only accepts an LLM connection. Keyless providers (`ollama`,
`hyperframes`) omit `apiKey` — `api_key_enc` is stored `NULL`. For TTS providers
the `model` field carries the voice/model id (e.g. `eleven_v3`, `aura-2-thalia-en`).

### `GET /api/connections` → `ProviderConnection[]`

```jsonc
// ProviderConnection (never return the raw key — apiKeyMasked only)
{
  "id": "c1",
  "provider": "openai",
  "model": "gpt-4o",
  "apiKeyMasked": "sk-…4a8f",
  "baseUrl": "http://localhost:11434",  // optional (self-hosted / ollama)
  "status": "ok",                        // unknown | ok | error
  "lastTestedAt": "2026-07-06T09:00:00Z" // optional
}
```

### `POST /api/connections`
Body: `{ provider, model, apiKey, baseUrl?, settings? }` (raw `apiKey` in, store
securely). → `ProviderConnection` with `status: "unknown"` and masked key.

### `DELETE /api/connections/:id`
Remove a connection. Any `AgentModelAssignment` pointing at it must be nulled.
→ `204`.

### `POST /api/connections/test`
Probe an **unsaved** connection straight from the add-connection form — nothing
is persisted. Body: `{ provider, model, apiKey?, baseUrl? }`. → `ConnectionTestResult`:

```jsonc
{ "success": true, "latencyMs": 214, "detail": "HTTP 200", "error": null }
```

The probe hits the provider's cheapest authenticated endpoint (its model/voice
list) — a 2xx means the key is valid and reachable; it spends no completion/TTS
credits. Keyless providers (`ollama`, `hyperframes`) skip the key. Never 500s —
failures come back as `success: false` with an `error` string.

### `POST /api/connections/:id/test`
Same probe for a **saved** connection (decrypts the stored key), and persists the
outcome onto the row (`status: "ok" | "error"`, `lastTestedAt` set).
→ `ConnectionTestResult`.

### `GET /api/assignments` → `AgentModelAssignment[]`

```jsonc
{ "role": "scriptwriter", "connectionId": "c1" }  // connectionId nullable
```

### `PUT /api/assignments/:role`
Body: `{ connectionId: string | null }`. → `AgentModelAssignment[]` (full list).

---

## Agent prompts

Editable prompt templates per agent, with reset-to-default.

### `GET /api/prompts` → `AgentPrompt[]`

```jsonc
// AgentPrompt
{
  "id": "comprehension",
  "label": "Comprehension",
  "template": "You are a research analyst…{{paper_text}}",
  "defaultTemplate": "You are a research analyst…{{paper_text}}",
  "variables": [
    { "name": "paper_text", "description": "Full parsed text of the source document" }
  ]
}
```

### `PUT /api/prompts/:id`
Body: `{ template: string }`. → updated `AgentPrompt`.

### `POST /api/prompts/:id/reset`
Reset `template` to `defaultTemplate`. → updated `AgentPrompt`.

---

## Render

### `GET /api/render/settings` → `RenderSettings`

```jsonc
// RenderSettings
{
  "fps": 30,                 // 24 | 30 | 60
  "width": 1920,
  "height": 1080,
  "quality": 82,             // 0..100
  "format": "mp4",           // mp4 | webm
  "codec": "h264",           // h264 | h265 | vp9 | av1
  "gpu": true,
  "workers": 4,
  "audioMasterDb": 0,
  "audioNarrationDb": -2,
  "audioMusicDb": -14
}
```

### `PUT /api/render/settings`
Body: `RenderSettings`. → saved `RenderSettings`.

### `POST /api/projects/:id/render` — WebSocket **or** SSE
Start a render with the given settings and stream progress. Body / query carries
`RenderSettings`. Emits `RenderJob`:

```jsonc
// RenderJob
{
  "id": "r1699999999",
  "status": "running",       // queued | running | done | error
  "progress": 0.42,          // 0..1
  "outputUrl": "https://…/video.mp4"  // present when status === "done"
}
```

The UI expects an initial `{ status: "running", progress: 0 }`, incremental
`running` events, and a final `done` carrying `outputUrl`.

---

## Notes for implementation

- **Statelessness of the UI:** the frontend keeps no source of truth beyond what
  these endpoints return — persistence, auth, and job orchestration are backend
  concerns.
- **Streaming transport:** the frontend abstracts pipeline/render behind a
  subscribe-callback with an unsubscribe cleanup, so either WebSocket or SSE is
  fine. Pick one and document the framing; JSON-per-message maps 1:1 to the
  event shapes above.
- **Security:** raw API keys go in on create/test only; every read returns
  `apiKeyMasked`. Never echo secrets.
- **Self-hosted:** `ProviderConnection.baseUrl` supports local providers
  (e.g. Ollama at `http://localhost:11434`); `apiKeyMasked` may be `"—"`.
