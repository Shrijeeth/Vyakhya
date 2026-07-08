// compile(doc) → HyperFrames-compatible HTML. One deterministic output used by
// both the browser editor (live preview) and the render worker (headless → MP4),
// guaranteeing preview == final.

import { registry, hasVisual } from "./registry.js";
import type { CompileOptions, SceneDocument, SceneNode } from "./types.js";
import { DEFAULT_AUTO_DURATION_MS, dimensions, esc } from "./util.js";

export function resolveDurationMs(
  scene: SceneNode,
  autoMs = DEFAULT_AUTO_DURATION_MS,
): number {
  const d = scene.durationMs;
  if (d === undefined || d === "auto") return autoMs;
  const n = Number(d);
  return Number.isFinite(n) && n > 0 ? n : autoMs;
}

/** Total composition duration in ms (resolves "auto" scenes). */
export function getCompositionDuration(
  doc: SceneDocument,
  autoMs = DEFAULT_AUTO_DURATION_MS,
): number {
  return doc.scenes.reduce((sum, s) => sum + resolveDurationMs(s, autoMs), 0);
}

function caption(scene: SceneNode): string {
  const style = scene.captionStyle ?? "none";
  if (style === "none" || !scene.narration) return "";
  return `<div class="hf-caption hf-caption-${style}">${esc(scene.narration)}</div>`;
}

function renderScene(scene: SceneNode, startMs: number, durationMs: number): string {
  const type = scene.visualType;
  const inner = hasVisual(type)
    ? registry[type](scene.params ?? {})
    : `<div class="hf-unknown">Unsupported visual: ${esc(type)}</div>`;
  const transition = scene.transition ?? "fade";
  return `<section class="clip hf-scene hf-transition-${transition}"
    data-scene-id="${esc(scene.id)}"
    data-start="${startMs}"
    data-duration="${durationMs}"
    data-visual="${esc(type)}">
    <div class="hf-stage">${inner}</div>
    ${caption(scene)}
  </section>`;
}

function themeCss(width: number, height: number): string {
  return `
  :root{--hf-bg:#faf7f0;--hf-fg:#1c1e2e;--hf-muted:#4a4f66;--hf-accent:#4b3fbf;--hf-accent-bg:#eae7ff}
  *{box-sizing:border-box}
  html,body{margin:0;padding:0;background:#000}
  .hf-composition{position:relative;width:${width}px;height:${height}px;margin:0 auto;
    background:var(--hf-bg);color:var(--hf-fg);overflow:hidden;
    font-family:Inter,system-ui,-apple-system,sans-serif}
  .hf-scene{position:absolute;inset:0;display:flex;flex-direction:column;
    align-items:center;justify-content:center;padding:6% 8%}
  .hf-stage{max-width:80%;text-align:center}
  .hf-h1{font-size:${Math.round(width / 24)}px;line-height:1.1;margin:0 0 .3em;letter-spacing:-0.02em}
  .hf-sub{font-size:${Math.round(width / 60)}px;color:var(--hf-muted);margin:0}
  .hf-bullets{list-style:none;padding:0;margin:0;text-align:left;font-size:${Math.round(width / 48)}px;line-height:1.6}
  .hf-bullet{margin:.2em 0}
  .hf-bullet::before{content:"›";color:var(--hf-accent);margin-right:.5em}
  .hf-figure{margin:0}
  .hf-figbox{border:2px dashed var(--hf-accent);border-radius:12px;padding:2em 3em;color:var(--hf-accent);font-size:${Math.round(width / 40)}px}
  .hf-figcap{margin-top:.6em;color:var(--hf-muted);font-size:${Math.round(width / 64)}px}
  .hf-equation code{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:${Math.round(width / 44)}px}
  .hf-dataviz{display:flex;flex-direction:column;gap:.6em;width:100%}
  .hf-bar{display:grid;grid-template-columns:8em 1fr auto;align-items:center;gap:.6em;font-size:${Math.round(width / 72)}px}
  .hf-bar-fill{height:1.4em;background:var(--hf-accent);border-radius:6px;width:var(--pct)}
  .hf-attention{display:flex;gap:.5em;flex-wrap:wrap;justify-content:center}
  .hf-token{background:var(--hf-accent-bg);color:var(--hf-accent);padding:.3em .7em;border-radius:8px;font-size:${Math.round(width / 40)}px}
  .hf-compare{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:1em;width:100%;font-size:${Math.round(width / 40)}px}
  .hf-compare-side{padding:1em;border-radius:12px;background:#fff}
  .hf-compare-divider{width:2px;height:60%;background:var(--hf-accent);opacity:.4}
  .hf-kinetic-word{font-size:${Math.round(width / 14)}px;font-weight:700;color:var(--hf-accent);letter-spacing:-0.03em}
  .hf-caption{position:absolute;left:0;right:0;bottom:6%;text-align:center;font-size:${Math.round(width / 56)}px;padding:0 8%}
  .hf-caption-minimal{color:var(--hf-fg)}
  .hf-caption-bold{color:#fff;font-weight:700;text-shadow:0 2px 12px rgba(0,0,0,.6)}
  .hf-unknown{color:#b00}`;
}

/**
 * Compile a Scene-JSON document into HyperFrames HTML.
 *
 * The output carries per-clip `data-start`/`data-duration` timing (ms) on a
 * single deterministic timeline; the HyperFrames runtime seeks it during
 * preview and render. Pass `fragment: true` to get just the composition node.
 */
export function compile(doc: SceneDocument, options: CompileOptions = {}): string {
  const autoMs = options.autoDurationMs ?? DEFAULT_AUTO_DURATION_MS;
  const { width, height } = dimensions(doc.aspectRatio);

  let cursor = 0;
  const scenes = doc.scenes
    .map((scene) => {
      const duration = resolveDurationMs(scene, autoMs);
      const html = renderScene(scene, cursor, duration);
      cursor += duration;
      return html;
    })
    .join("\n");

  const total = cursor;
  const composition = `<main class="hf-composition" data-hf-composition
    data-duration="${total}" data-width="${width}" data-height="${height}"
    data-aspect="${esc(doc.aspectRatio)}" data-project="${esc(doc.id)}">
${scenes}
  </main>`;

  if (options.fragment) return composition;

  // Preview-only: center + scale the fixed-pixel composition to fit the iframe.
  const fitCss = options.fit
    ? `html,body{height:100%}body{display:grid;place-items:center;overflow:hidden}`
    : "";
  const fitScript = options.fit
    ? `<script>(function(){var c=document.querySelector('.hf-composition');if(!c)return;function f(){var s=Math.min(innerWidth/${width},innerHeight/${height});c.style.transform='scale('+s+')';c.style.transformOrigin='center center';}addEventListener('resize',f);f();})();</script>`
    : "";

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${esc(doc.title)}</title>
<style>${themeCss(width, height)}${fitCss}</style>
</head>
<body>
${composition}
${fitScript}
</body>
</html>`;
}
