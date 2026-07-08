# Vyakhya — Ideation

## 1. Problem
Researchers, students, educators, and analysts drown in dense PDFs. Reading a 30-page paper takes hours; understanding it takes more. Existing "doc → video" tools exist but fall short:

- **NotebookLM Video Overview** — black box. 2 videos/day (non-Ultra), no script editing, no visual-style control, no timeline edit, "may contain inaccuracies," can take 30+ min. You accept it or regenerate.
- **Commercial PDF→video (Brainy Docs, Scholarly, NoteGPT)** — mostly shallow slideshow + TTS. Little real reasoning about the paper; weak on math/figures; closed source; per-video credits.
- **Academic systems (Paper2Video, Preacher)** — genuinely multi-agent and high quality, but they are research artifacts, not usable products, and not maintained as a platform.

**Gap:** No tool gives a *deep, accurate, editable, self-hostable* paper→video pipeline. That is the whole thesis.

## 2. Solution
An **open-source multi-agent** system that ingests a paper/PDF and produces a detailed explainer video. Agents collaborate rather than a single prompt doing everything:

1. **Ingestor** — parse PDF (text, sections, figures, tables, equations, references). Layout-aware (GROBID / Nougat / marker-style).
2. **Comprehension agent** — build a structured understanding: claims, method, results, contributions. Grounds every fact to a source span.
3. **Planner / Director** — decide the video outline: hook → context → method → results → implications. Allocates runtime per section (this is what makes it *detailed*, not a 90s summary).
4. **Scriptwriter** — narration per scene, tuned to audience level (layperson / student / expert).
5. **Visual designer** — for each scene choose the visual: figure callout, animated diagram, equation build-up, data-viz, kinetic typography. Emits **HyperFrames HTML**.
6. **Narrator** — TTS (BYO: Kokoro local / ElevenLabs / HeyGen).
7. **Verifier / Fact-checker** — adversarial pass: does narration match source? Flag hallucinations before render. (Directly attacks NotebookLM's #1 weakness.)
8. **Editor / Assembler** — stitch scenes, transitions, captions, BGM; render via HyperFrames to MP4.

Output is **code, not a black-box MP4** — user can open the project, edit any scene/script/voice, and re-render deterministically.

## 3. Name — Vyakhya (locked)
**Vyakhya** (व्याख्या) — Sanskrit/Hindi for *explanation, exposition, commentary*. The name **is** the product: it turns a paper into a spoken, visual exposition. Short, distinctive, culturally rooted, and — verified via search — no existing AI company/product owns it (only individual GitHub users).

### Candidates considered

| Name | Meaning | Verdict |
|------|---------|---------|
| **Vyakhya** ⭐ | explanation / exposition / commentary | **Chosen** — literal fit, available |
| Chitrakatha | picture-story (cf. Amar Chitra Katha) | Available; strong but longer to spell/type |
| Vivaran | detailed account / description | Available; good backup |
| Drishya | the seen / scene / visual | ❌ taken (Drishya AI Labs, funded) |
| Manthan | churning (of knowledge) | ❌ taken (Manthan analytics, Bengaluru) |
| Saar / Saaransh | summary / essence | ❌ semantically wrong — we build *detailed*, not summaries |
| Paperframe (English, earlier pick) | paper → frames | ❌ GitHub repo collision (Framesia/paperframe) |

**Backups:** Vivaran, then Chitrakatha. **Before committing:** grab domain (.ai / .dev / .video), npm, GitHub org, and do a trademark sanity check.

## 4. Feature roadmap
**MVP (v0.1)**
- PDF upload → structured parse
- 3–5 agent pipeline (ingest, plan, script, visual, narrate)
- HyperFrames render to MP4
- 2–3 visual templates, 1 TTS provider
- CLI + minimal web UI

**v0.5**
- Verifier agent + citation overlays (click a claim → source span)
- Audience-level toggle (ELI5 / student / expert)
- Multiple visual styles, BGM, chapter markers
- BYO-model config (OpenAI / Anthropic / local Ollama)

**v1.0**
- Web editor: tweak script/scene/voice, re-render
- Multi-paper / literature-review mode (survey video across N papers)
- Figure animation (bring static charts to life)
- Export: MP4, slides (PPTX), transcript, flashcards
- Hosted cloud option (managed render, no setup)

**Later**
- Presenter avatar (opt-in)
- 70+ language output
- Slack/Notion/LMS integrations
- Community template registry (visual styles as shareable blocks)

## 5. Open-source strategy
**Model: open-core + managed cloud.**

- **Core (Apache-2.0):** full agent pipeline, CLI, render engine glue, self-host. Free forever, BYO API keys, BYO GPU. No daily caps — direct contrast to NotebookLM's 2/day.
- **Managed cloud (paid):** hosted rendering, no setup, team workspaces, storage, faster GPUs, priority queue. Usage/seat pricing.
- **Enterprise:** SSO, on-prem, private-model routing, audit logs, SLA. Key for pharma/legal/gov research where data can't leave.

**Why OSS wins here:**
- **Privacy** — sensitive/unpublished research never leaves the org. Huge for labs, pharma, law, defense.
- **Trust & accuracy** — verifier + citation logic is auditable; academics trust what they can inspect.
- **Distribution** — GitHub stars + arXiv/ML Twitter/HN reach the exact ICP (researchers) for free.
- **Extensibility** — community contributes visual templates, parsers, TTS/model adapters.

**License nuance:** consider Apache-2.0 for max adoption. If cloud-cannibalization risk grows, evaluate a source-available license (BSL/AGPL) for specific hosted-only modules — but keep the core permissive to win developer trust.

**Community moat:** template registry, model/TTS adapter ecosystem, and a benchmark for "faithful paper→video" that others cite. First mover in OSS here compounds.

## 6. Key risks & mitigations
| Risk | Mitigation |
|------|-----------|
| Hallucination / wrong explanations | Verifier agent + citation grounding + source-span overlays |
| Render cost / compute | HyperFrames is HTML→video (cheap, deterministic); offload heavy TTS/LLM to BYO keys |
| Google ships depth in NotebookLM | Compete on openness, editability, privacy, self-host — things Google won't do |
| Quality of auto visuals | Curated template library + human-editable output as safety net |
| Slow adoption | Nail one wedge first: ML/CS researchers making explainers of their own papers |

## 7. Wedge / GTM
Start narrow: **researchers turning their own papers into explainer/teaser videos** (conference promo, lab websites, social). They're technical (OSS-friendly), need accuracy, and already share on the channels where OSS spreads. Expand to students → educators → analysts/enterprise.
