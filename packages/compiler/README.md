# @vyakhya/compiler

Shared **TypeScript** package: **Scene-JSON → HyperFrames HTML**.

Imported by **both**:

- the **browser editor** (`frontend/`) — client-side compile for instant live preview
- the **render service** (`render/`) — same compile before headless render

→ guarantees **preview == final**. Deterministic (no randomness), seek-safe.

## API

```ts
import { compile, getCompositionDuration } from "@vyakhya/compiler";

const html = compile(sceneDocument); // full HTML doc (or { fragment: true })
const ms = getCompositionDuration(sceneDocument); // resolves "auto" scenes
```

## Structure

- `types.ts` — Scene-JSON types (mirror the backend Pydantic `SceneDocument`;
  destined to be generated from its JSON Schema).
- `registry.ts` — one renderer per `visual.type` (`title.card`, `bullet.reveal`,
  `figure.callout`, `equation.build`, `dataviz.bar`, `diagram.attention`,
  `comparison.split`, `kinetic.type`). New visual = new registry entry.
- `compile.ts` — lays scenes on a single deterministic timeline (per-clip
  `data-start` / `data-duration`), wraps them in a `data-hf-composition` root,
  and emits the themed HTML the HyperFrames runtime seeks.

## Dev

```bash
bun run build      # tsc → dist/
bun run typecheck
bun run test       # vitest
```
