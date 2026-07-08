# Vyakhya Database Schema

Postgres schema for the Studio backend, derived from the frontend domain model
([`frontend/src/services/types.ts`](../frontend/src/services/types.ts)), the wire
contract ([`api.md`](api.md)), and the architecture ([`architecture.md`](architecture.md)).

**Scope assumptions** (from the README): self-hosted, **single-workspace**,
bring-your-own-keys. So there is **no users / auth / multi-tenant** table — every
row is owned by the one local workspace. Add a `workspace_id` later only if
hosted multi-tenant is ever in scope.

Conventions:
- Primary keys are `text` (opaque IDs like `p1`, `s1`, `c1`) to match the API
  and keep them URL/JSON friendly. Use app-generated IDs (or swap to `uuid` with
  `gen_random_uuid()` if you prefer DB-generated).
- Timestamps are `timestamptz` (UTC).
- Enums are Postgres `ENUM` types (listed first) so the DB enforces the same
  value sets the TS union types do.
- Flexible / schema-driven blobs (`Scene.params`, prompt `variables`) are `jsonb`.

---

## Enum types

```sql
CREATE TYPE project_status   AS ENUM ('draft', 'generating', 'ready', 'failed');
CREATE TYPE audience_level   AS ENUM ('layperson', 'student', 'expert');
CREATE TYPE aspect_ratio     AS ENUM ('16:9', '9:16', '1:1');

CREATE TYPE agent_id         AS ENUM (
  'ingestor', 'comprehension', 'planner', 'scriptwriter',
  'visual_designer', 'narrator', 'verifier', 'assembler'
);
CREATE TYPE agent_status     AS ENUM ('queued', 'running', 'done', 'error');

-- Roles that get a model assigned (subset of agent_id: no ingestor/assembler)
CREATE TYPE agent_role       AS ENUM (
  'comprehension', 'planner', 'scriptwriter', 'visual_designer', 'narrator', 'verifier'
);

CREATE TYPE visual_type      AS ENUM (
  'title.card', 'bullet.reveal', 'figure.callout', 'equation.build',
  'dataviz.bar', 'diagram.attention', 'comparison.split', 'kinetic.type'
);
CREATE TYPE caption_style    AS ENUM ('none', 'minimal', 'bold');
CREATE TYPE scene_transition AS ENUM ('cut', 'fade', 'slide', 'wipe');

CREATE TYPE provider_id      AS ENUM ('openai', 'anthropic', 'elevenlabs', 'ollama', 'gemini', 'groq');
CREATE TYPE connection_status AS ENUM ('unknown', 'ok', 'error');

CREATE TYPE verifier_level   AS ENUM ('pass', 'warn', 'fail');
CREATE TYPE render_status     AS ENUM ('queued', 'running', 'done', 'error');
CREATE TYPE video_format      AS ENUM ('mp4', 'webm');
CREATE TYPE video_codec       AS ENUM ('h264', 'h265', 'vp9', 'av1');
```

---

## Tables

### `projects`
One row per paper-to-video project. Maps to `Project` / `EditorProject` (the
editor's `title` + `aspectRatio` live here; scenes are child rows).

```sql
CREATE TABLE projects (
  id                text PRIMARY KEY,
  title             text NOT NULL,
  source_paper      text NOT NULL,            -- citation / display name
  paper_file_url    text,                     -- stored PDF (MinIO/S3 key or URL)
  thumbnail_url     text,
  status            project_status NOT NULL DEFAULT 'draft',
  audience          audience_level NOT NULL,
  aspect_ratio      aspect_ratio   NOT NULL DEFAULT '16:9',
  language          text NOT NULL DEFAULT 'en',
  target_length_min integer,                  -- requested length (from create)
  duration_ms       integer NOT NULL DEFAULT 0, -- final/known video duration
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX projects_status_idx      ON projects (status);
CREATE INDEX projects_updated_at_idx  ON projects (updated_at DESC);
```

> `GET /api/projects` returns these rows; `duration_ms` stays `0` until a render
> exists. `total_duration_ms` in the editor is the sum of scene durations (compute
> on read, or cache here).

### `scenes`
Editable timeline rows — the **Scene-JSON** source of truth (§2 of architecture).
`params` is `jsonb` because its shape depends on `visual_type` (see the
params-by-visualType table in [`api.md`](api.md)).

```sql
CREATE TABLE scenes (
  id            text PRIMARY KEY,
  project_id    text NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  position      integer NOT NULL,             -- 1-based order ("index" in the API)
  narration     text NOT NULL DEFAULT '',
  visual_type   visual_type NOT NULL,
  params        jsonb NOT NULL DEFAULT '{}',  -- shape keyed by visual_type
  caption_style caption_style NOT NULL DEFAULT 'minimal',
  transition    scene_transition NOT NULL DEFAULT 'fade',
  duration_ms   integer,                      -- NULL == "auto"
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, position)
);

CREATE INDEX scenes_project_idx ON scenes (project_id, position);
```

> API `Scene.index` → `position`. `Scene.durationMs` is `number | "auto"`; model
> `"auto"` as SQL `NULL`. `PUT /scenes/:id` upserts one row; reordering rewrites
> `position` (do it in a transaction to respect the `UNIQUE` constraint —
> e.g. offset by a large delta, then renumber).

### `scene_citations`
Per-scene citation grounding (`Scene.citations[]`). Kept relational for querying;
could alternatively be `jsonb` on `scenes`.

```sql
CREATE TABLE scene_citations (
  id          text PRIMARY KEY,
  scene_id    text NOT NULL REFERENCES scenes (id) ON DELETE CASCADE,
  label       text NOT NULL,                  -- e.g. "[1]"
  source_span text NOT NULL,                  -- e.g. "§1.1, p. 3"
  position    integer NOT NULL DEFAULT 0
);

CREATE INDEX scene_citations_scene_idx ON scene_citations (scene_id, position);
```

---

## Pipeline

### `pipeline_runs`
One row per agent-crew execution of a project (created when generation starts).

```sql
CREATE TABLE pipeline_runs (
  id          text PRIMARY KEY,
  project_id  text NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  status      agent_status NOT NULL DEFAULT 'queued', -- overall
  progress    real NOT NULL DEFAULT 0,        -- 0..1
  started_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);

CREATE INDEX pipeline_runs_project_idx ON pipeline_runs (project_id, started_at DESC);
```

### `agent_node_states`
Per-agent status within a run (`AgentNodeState`) — powers the React Flow DAG.

```sql
CREATE TABLE agent_node_states (
  id          bigserial PRIMARY KEY,
  run_id      text NOT NULL REFERENCES pipeline_runs (id) ON DELETE CASCADE,
  agent       agent_id NOT NULL,
  label       text NOT NULL,
  status      agent_status NOT NULL DEFAULT 'queued',
  elapsed_ms  integer NOT NULL DEFAULT 0,
  result      jsonb,                          -- optional agent output
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, agent)
);
```

### `pipeline_events`
Append-only log/status/progress stream (`PipelineEvent`). Source for the live
WS/SSE feed and for replay on reconnect.

```sql
CREATE TABLE pipeline_events (
  id         bigserial PRIMARY KEY,
  run_id     text NOT NULL REFERENCES pipeline_runs (id) ON DELETE CASCADE,
  type       text NOT NULL,                   -- 'status' | 'log' | 'flag' | 'progress' | 'done'
  agent      agent_id,                         -- nullable (progress/done have none)
  payload    jsonb NOT NULL,                   -- string | number | VerifierFlag | null
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX pipeline_events_run_idx ON pipeline_events (run_id, id);
```

### `verifier_flags`
Claim-grounding results (`VerifierFlag`) emitted by the verifier agent.

```sql
CREATE TABLE verifier_flags (
  id          text PRIMARY KEY,
  project_id  text NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  run_id      text REFERENCES pipeline_runs (id) ON DELETE SET NULL,
  claim       text NOT NULL,
  source_span text NOT NULL,
  level       verifier_level NOT NULL,
  note        text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX verifier_flags_project_idx ON verifier_flags (project_id, created_at DESC);
```

> `GET /api/projects/:id/verifier-flags` reads the latest set for a project.

---

## Model configuration

### `provider_connections`
LLM/TTS provider credentials (`ProviderConnection`). **The raw API key is never
returned** by the API (`apiKeyMasked` only) — store it **encrypted at rest** with
`VYAKHYA_ENCRYPTION_KEY` (see README). Keep a masked display copy for the UI.

```sql
CREATE TABLE provider_connections (
  id             text PRIMARY KEY,
  provider       provider_id NOT NULL,
  model          text NOT NULL,
  api_key_enc    bytea,                        -- encrypted secret (NULL for keyless, e.g. ollama)
  api_key_masked text NOT NULL DEFAULT '—',    -- safe to return to the UI
  base_url       text,                         -- self-hosted / ollama endpoint
  status         connection_status NOT NULL DEFAULT 'unknown',
  last_tested_at timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now()
);
```

### `agent_model_assignments`
Which connection powers each agent role (`AgentModelAssignment`). One row per
role; `connection_id` nulled on connection delete.

```sql
CREATE TABLE agent_model_assignments (
  role          agent_role PRIMARY KEY,
  connection_id text REFERENCES provider_connections (id) ON DELETE SET NULL,
  updated_at    timestamptz NOT NULL DEFAULT now()
);
```

> `DELETE /api/connections/:id` must null any assignment pointing at it — the
> `ON DELETE SET NULL` above enforces this at the DB level.

### `agent_prompts`
Editable prompt templates per agent (`AgentPrompt`). `default_template` is the
factory reset target; `variables` is the declared interpolation schema.

```sql
CREATE TABLE agent_prompts (
  id               agent_id PRIMARY KEY,       -- one prompt per agent
  label            text NOT NULL,
  template         text NOT NULL,
  default_template text NOT NULL,
  variables        jsonb NOT NULL DEFAULT '[]', -- [{ name, description }]
  updated_at       timestamptz NOT NULL DEFAULT now()
);
```

> `POST /api/prompts/:id/reset` sets `template = default_template`.

---

## Render

### `render_settings`
Global (single-workspace) render defaults (`RenderSettings`). Single-row table;
pin it with a `CHECK` so there's exactly one. (Promote to per-project by adding a
`project_id` PK if per-project overrides are ever needed.)

```sql
CREATE TABLE render_settings (
  id                 boolean PRIMARY KEY DEFAULT true CHECK (id),  -- single row guard
  fps                smallint NOT NULL DEFAULT 30 CHECK (fps IN (24, 30, 60)),
  width              integer  NOT NULL DEFAULT 1920,
  height             integer  NOT NULL DEFAULT 1080,
  quality            smallint NOT NULL DEFAULT 82 CHECK (quality BETWEEN 0 AND 100),
  format             video_format NOT NULL DEFAULT 'mp4',
  codec              video_codec  NOT NULL DEFAULT 'h264',
  gpu                boolean NOT NULL DEFAULT true,
  workers            smallint NOT NULL DEFAULT 4,
  audio_master_db    real NOT NULL DEFAULT 0,
  audio_narration_db real NOT NULL DEFAULT -2,
  audio_music_db     real NOT NULL DEFAULT -14,
  updated_at         timestamptz NOT NULL DEFAULT now()
);
```

### `render_jobs`
A single render invocation (`RenderJob`) — streamed progress + final output.

```sql
CREATE TABLE render_jobs (
  id          text PRIMARY KEY,
  project_id  text NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  status      render_status NOT NULL DEFAULT 'queued',
  progress    real NOT NULL DEFAULT 0,         -- 0..1
  output_url  text,                            -- set when status = 'done'
  settings    jsonb NOT NULL,                  -- snapshot of RenderSettings used
  error       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);

CREATE INDEX render_jobs_project_idx ON render_jobs (project_id, created_at DESC);
```

---

## Background jobs (Procrastinate)

Async orchestration (pipeline runs, renders) is driven by **Procrastinate**,
which owns its own tables in a dedicated schema — **do not hand-model these**;
they are created by `procrastinate schema --apply` (migrations).

```sql
CREATE SCHEMA IF NOT EXISTS procrastinate;
-- procrastinate_jobs, procrastinate_events, procrastinate_periodic_defers, …
-- managed entirely by Procrastinate's migrations.
```

Link app rows to jobs by storing the Procrastinate job id on `pipeline_runs` /
`render_jobs` if you need to cancel or introspect them:

```sql
ALTER TABLE pipeline_runs ADD COLUMN procrastinate_job_id bigint;
ALTER TABLE render_jobs   ADD COLUMN procrastinate_job_id bigint;
```

---

## Entity relationships

```text
projects 1───∞ scenes 1───∞ scene_citations
   │
   ├───∞ pipeline_runs 1───∞ agent_node_states
   │            │        1───∞ pipeline_events
   │            └────────∞ verifier_flags
   │
   └───∞ render_jobs

provider_connections 1───∞ agent_model_assignments (by role)
agent_prompts   (standalone, one row per agent_id)
render_settings (standalone, single row)
```

## Migration / ORM notes

- The backend is FastAPI + Agno (Python). If using SQLAlchemy + Alembic, mirror
  these `ENUM`s as `sqlalchemy.Enum(..., name='...')` and let Alembic emit
  `CREATE TYPE`. Procrastinate migrations run separately.
- **Scene-JSON stays canonical.** The Pydantic `Scene` model (Agno
  `output_schema`) is the source of truth; the `scenes` + `scene_citations`
  tables are its persisted, editable form. Keep column names aligned with the TS
  contract so `api.md` responses serialize with minimal mapping.
- Set `updated_at` via a trigger or in the app layer on every write.
- Secrets: only `provider_connections.api_key_enc` holds sensitive data —
  encrypt with `VYAKHYA_ENCRYPTION_KEY`, never log or return it.
```
