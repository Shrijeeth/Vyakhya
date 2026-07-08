# @vyakhya/compiler

Shared **TypeScript** package: **Scene-JSON → HyperFrames HTML**.

Imported by **both**:
- the **browser editor** (`apps/web`) — client-side compile for instant live preview
- the **render service** (`services/render`) — same compile before headless render

→ guarantees **preview == final**. Deterministic (no randomness), seek-safe.

Core pieces:
- `types.ts` — **generated** from the API's Scene-JSON Pydantic JSON Schema (CI checks for drift).
- `registry/` — one entry per `visual.type` (`title.card`, `figure.callout`, `equation.build`, `diagram.*`, `dataviz.*`, …). New block = new registry entry.
- `compile(videoDoc): string` — dispatch each scene's `visual.type` to its block, attach timing/captions/transitions, wrap in a HyperFrames composition.

> Scaffold placeholder — schema generation + registry land here next. See `docs/scene-schema.md`.
