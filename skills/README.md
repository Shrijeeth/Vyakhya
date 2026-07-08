# skills/ — HyperFrames agent skills

Vendored **HyperFrames** agent skills from
[heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) (Apache-2.0).
HyperFrames renders video from HTML — a composition is an HTML file whose DOM
declares timing with `data-*` attributes. These skills teach an agent the
production loop: plan → write valid HTML → wire seekable animations → lint →
preview → render.

## What's here

The essential subset for a paper → explainer-video workflow:

| Skill | Role |
|-------|------|
| [`hyperframes/`](hyperframes/SKILL.md) | **Entry / router** — read first; routes a request to the right workflow. |
| [`hyperframes-core/`](hyperframes-core/SKILL.md) | The authoring contract: data-attributes, determinism rules, script/storyboard format. |
| [`hyperframes-cli/`](hyperframes-cli/SKILL.md) | Lint · validate · preview · render via the CLI. |
| [`hyperframes-keyframes/`](hyperframes-keyframes/SKILL.md) | Keyframe animation patterns. |
| [`hyperframes-registry/`](hyperframes-registry/SKILL.md) | Authoring reusable blocks/components. |
| [`faceless-explainer/`](faceless-explainer/SKILL.md) | End-to-end faceless explainer workflow (closest to Vyakhya's output). |

The upstream repo ships **20 skills** in total (animation, creative, motion-graphics,
slideshow, website-to-video, …). Install the full set with:

```bash
npx skills add heygen-com/hyperframes --all
```

## How Vyakhya uses them

The backend loads this directory as Agno **`LocalSkills`** for the design-time
visual-designer / block-author agent, so it authors HyperFrames-valid HTML
(and `@vyakhya/compiler` `visual.type` blocks) using the same contract the
render service (`render/`, `@hyperframes/producer`) enforces.

```python
from agno.skills import Skills, LocalSkills
visual_designer = Agent(model=..., skills=Skills(loaders=[LocalSkills("./skills")]))
```

Source: <https://github.com/heygen-com/hyperframes> · License: Apache-2.0 (see the
upstream `LICENSE`). Fonts/media assets and the large animation/creative recipe
libraries are intentionally omitted — add them with the `npx skills add` command
above if a workflow needs them.
