<div align="center">

# Vyakhya · व्याख्या

**Open-source, multi-agent engine that turns any paper or PDF into a detailed, editable explainer video.**

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Status](https://img.shields.io/badge/status-early%20development-orange.svg)
![Self-host](https://img.shields.io/badge/deploy-self--host-brightgreen.svg)

</div>

---

## What is Vyakhya?

**Vyakhya** (Sanskrit *व्याख्या* — "explanation, exposition") reads a research paper and a crew of AI agents collaborate to produce a **detailed, section-by-section explainer video** — figures, equations, and all. Unlike black-box tools, the output is **structured and editable**: you tweak scenes and narration in an editor, not raw HTML, and re-render deterministically. It runs **entirely on your own machine**.

- 🧠 **Multi-agent depth** — read → comprehend → plan → script → visualize → narrate → **verify** → assemble. Not a 90-second summary.
- ✍️ **Editable, not a black box** — the video is data (Scene-JSON) rendered to HTML; edit any scene, then re-render.
- 🔒 **Self-hosted & private** — your papers and API keys never leave your infra.
- 🔌 **Bring your own models** — OpenAI, Anthropic, or local via Ollama. Your keys.
- ✅ **Accuracy-first** — a verifier agent grounds every claim to a source span.
- 🎬 **HTML-native rendering** — deterministic, code-based video via HyperFrames.

> **Scope: self-host OSS only.** Single-workspace, bring-your-own-keys, uncapped renders. No hosted/cloud version.

## The app: Vyakhya Studio

Vyakhya is **one app — Studio** — a FastAPI backend (Agno agents) that serves the React frontend, backed by a Postgres job queue and a Node render service. (The marketing landing site is separate and hosted on Lovable — not in this repo.)

```
PDF ─▶ Studio backend (Python · FastAPI · Agno agents) ─▶ Scene-JSON ─┬─▶ Studio frontend: live HTML preview
                     │                                                 │      (@vyakhya/compiler in the browser)
              Procrastinate jobs                                       └─▶ Render service (Node · @hyperframes/producer)
              (Postgres, async)                                             compile → lint → render ─▶ MP4 ─▶ MinIO/S3
```

**Scene-JSON** is the contract crossing all boundaries: defined once as Pydantic (Agno `output_schema`), the TS type generated from its JSON Schema. See [`docs/`](docs/).

## Repository layout

| Path | What |
|------|------|
| [`frontend/`](frontend/) | React + Vite Studio UI (dashboard, agent pipeline view, scene editor, model config, render settings) |
| [`backend/`](backend/) | Python · FastAPI · **Agno** orchestration · **Procrastinate** jobs · emits Scene-JSON · serves the frontend |
| [`render/`](render/) | Node · **@hyperframes/producer** · compile → lint → render → MP4 |
| [`packages/compiler/`](packages/compiler/) | **@vyakhya/compiler** — Scene-JSON → HyperFrames HTML (shared: browser + render) |
| [`skills/hyperframes/`](skills/hyperframes/) | HyperFrames Agno `LocalSkills` dir (design-time block authoring) |
| [`docs/`](docs/) | Architecture, Scene-JSON schema, decisions |
| [`docker-compose.yml`](docker-compose.yml) | `studio + worker + render + postgres + minio` |
| [`setup.sh`](setup.sh) | Scripted install: generate key, write `.env`, migrate, `docker compose up` |

## Quick start (self-host)

```bash
git clone https://github.com/Shrijeeth/Vyakhya.git
cd Vyakhya
./setup.sh            # generates encryption key, writes .env, brings up the stack
# open the printed URL, add your model provider keys in the UI, upload a PDF
```

Requires Docker. The setup script provisions `VYAKHYA_ENCRYPTION_KEY` (used to encrypt your provider keys at rest) into `.env` — keep that file private and backed up.

## Tech stack

**Frontend:** React · Vite · TypeScript · Tailwind · shadcn/ui · React Flow · Monaco · BlockNote · Vidstack
**Backend:** Python · FastAPI · Agno · Procrastinate · Postgres
**Render:** Node · HyperFrames (`@hyperframes/producer`) · FFmpeg · headless Chrome
**Shared:** `@vyakhya/compiler` (TS) · Scene-JSON contract · MinIO/S3

## Status

Early development. See [`docs/`](docs/) for the design and [issues](https://github.com/Shrijeeth/Vyakhya/issues) for the roadmap. Contributions welcome.

## License

[Apache-2.0](LICENSE).
