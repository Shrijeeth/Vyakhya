// compile(doc) → HyperFrames-compatible HTML. One deterministic output used by
// both the browser editor (live preview) and the render worker (headless → MP4),
// guaranteeing preview == final.
//
// The output follows the HyperFrames composition contract (skills/hyperframes-core):
//   - one root element with data-composition-id / data-width / data-height /
//     data-duration (seconds)
//   - every timed element is a `class="clip"` DIRECT child of the root with
//     id / data-start / data-duration (seconds) / data-track-index
//   - motion is finite CSS keyframes offset to each clip's start via the
//     `--t0` custom property (seek-safe, no clocks, no randomness)

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

const sec = (ms: number) => (Math.round(ms) / 1000).toString();

function caption(scene: SceneNode): string {
  const style = scene.captionStyle ?? "none";
  if (style === "none" || !scene.narration) return "";
  return `<div class="hf-caption hf-caption-${style}">${esc(scene.narration)}</div>`;
}

function renderScene(
  scene: SceneNode,
  index: number,
  startMs: number,
  durationMs: number,
): string {
  const type = scene.visualType;
  const inner = hasVisual(type)
    ? registry[type](scene.params ?? {})
    : `<div class="hf-unknown">Unsupported visual: ${esc(type)}</div>`;
  const transition = scene.transition ?? "fade";
  // Agent-authored scenes design the FULL frame — bypass the centered stage
  // box so their height:100% backgrounds actually fill the canvas.
  const stageClass = type === "custom.html" ? "hf-stage hf-stage-full" : "hf-stage";
  // `--t0` shifts every entrance animation to the clip's start so the same
  // markup is correct in the seek-driven preview AND the HyperFrames render.
  return `<section class="clip hf-scene hf-transition-${transition}"
    id="scene-${index}"
    style="--t0:${sec(startMs)}s"
    data-scene-id="${esc(scene.id)}"
    data-start="${sec(startMs)}"
    data-duration="${sec(durationMs)}"
    data-track-index="0"
    data-visual="${esc(type)}">
    <div class="${stageClass}">${inner}</div>
    ${caption(scene)}
  </section>`;
}

function themeCss(width: number, height: number): string {
  return `
  :root{--hf-bg:#faf7f0;--hf-fg:#1c1e2e;--hf-muted:#4a4f66;--hf-accent:#4b3fbf;--hf-accent-bg:#eae7ff}
  *{box-sizing:border-box}
  html,body{margin:0;padding:0;background:#000}
  .hf-composition{position:relative;width:${width}px;height:${height}px;
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
  .hf-figure{margin:0;display:flex;flex-direction:column;align-items:center;gap:.6em;max-width:100%}
  audio.clip{display:none}
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
  .hf-kinetic-word{display:inline-block;font-size:${Math.round(width / 14)}px;font-weight:700;color:var(--hf-accent);letter-spacing:-0.03em}
  .hf-figimg{max-width:100%;max-height:${Math.round(height * 0.62)}px;border-radius:12px;
    box-shadow:0 24px 60px -24px rgba(28,30,46,.35);background:#fff;padding:8px}
  .hf-orbit{perspective:${Math.round(width * 0.7)}px;--hf-orbit-r:${Math.round(width / 5.5)}px}
  .hf-orbit-ring{position:relative;width:1px;height:1px;margin:0 auto;transform-style:preserve-3d;
    animation:hf-orbit-spin 24s linear both;animation-iteration-count:4;animation-delay:var(--t0,0s)}
  .hf-orbit-card{position:absolute;left:50%;top:50%;width:${Math.round(width / 6)}px;margin-left:-${Math.round(width / 12)}px;
    margin-top:-${Math.round(width / 36)}px;padding:.5em .8em;border-radius:12px;background:#fff;
    box-shadow:0 10px 30px -12px rgba(28,30,46,.3);text-align:center;
    font-size:${Math.round(width / 60)}px;font-weight:600;color:var(--hf-fg);backface-visibility:hidden}
  .hf-custom{width:100%;height:100%;display:flex;align-items:center;justify-content:center;
    container-type:size}
  .hf-custom>:not(style){flex:1 1 100%;width:100%;height:100%;min-height:100%}
  .hf-stage-full{position:absolute;inset:0;max-width:none;width:100%;height:100%;text-align:initial;
    background:#10131f;color:#f4f6fb}
  .hf-caption{position:absolute;left:50%;bottom:4%;transform:translateX(-50%);max-width:84%;
    text-align:center;font-size:${Math.round(width / 56)}px;padding:.4em 1em;border-radius:12px;
    background:rgba(8,10,18,.55);color:#fff;backdrop-filter:blur(6px)}
  .hf-caption-minimal{font-weight:400}
  .hf-caption-bold{font-weight:700;text-shadow:0 2px 12px rgba(0,0,0,.6)}
  .hf-unknown{color:#b00}
  /* Entrance animations, offset to each clip's start (--t0) with per-element
     stagger (--i). Finite + property-allowlisted → seekable and render-safe. */
  @keyframes hf-rise{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:none}}
  @keyframes hf-in{from{opacity:0;transform:translateX(-16px)}to{opacity:1;transform:none}}
  @keyframes hf-grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
  @keyframes hf-pop{from{opacity:0;transform:scale(.6)}to{opacity:1;transform:none}}
  @keyframes hf-slide-in{from{opacity:0;transform:translateX(90px)}to{opacity:1;transform:none}}
  @keyframes hf-wipe-in{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
  @keyframes hf-orbit-spin{from{transform:rotateY(0)}to{transform:rotateY(360deg)}}
  .hf-stage{animation:hf-rise .6s both ease-out;animation-delay:var(--t0,0s)}
  /* The scene's transition shapes its stage entrance — cuts snap, slides
     sweep, wipes reveal — so pacing varies scene to scene. */
  .hf-transition-cut .hf-stage{animation-duration:.01s}
  .hf-transition-slide .hf-stage{animation-name:hf-slide-in;animation-duration:.7s}
  .hf-transition-wipe .hf-stage{animation-name:hf-wipe-in;animation-duration:.8s}
  .hf-bullet{animation:hf-in .5s both ease-out;animation-delay:calc(var(--t0,0s) + .15s + var(--i,0)*.12s)}
  .hf-bar-fill{transform-origin:left center;animation:hf-grow .7s both ease-out;animation-delay:calc(var(--t0,0s) + .1s + var(--i,0)*.15s)}
  .hf-token{animation:hf-pop .4s both ease-out;animation-delay:calc(var(--t0,0s) + var(--i,0)*.06s)}
  .hf-kinetic-word{animation:hf-pop .5s both ease-out;animation-delay:var(--t0,0s)}`;
}

// Injected into preview docs only. Every animation in the composition (built-in
// AND agent-authored) declares its delay as calc(var(--t0) + offset), so
// seeking is one variable write: pause everything, set the active scene's
// --t0 to -localTime, and the paused animations resolve to that exact frame.
function previewRuntime(): string {
  return `<style>*{animation-play-state:paused !important}</style>
<script>(function(){var scenes=[].slice.call(document.querySelectorAll('.hf-scene'));
var audios=[].slice.call(document.querySelectorAll('audio.clip'));var playing=false;
function syncAudio(t){for(var i=0;i<audios.length;i++){var a=audios[i],s=1000*(parseFloat(a.getAttribute('data-start'))||0),d=1000*(parseFloat(a.getAttribute('data-duration'))||0),act=playing&&t>=s&&t<s+d;
if(act){var off=(t-s)/1000;if(Math.abs(a.currentTime-off)>0.3){try{a.currentTime=off;}catch(_){}}
if(a.paused){var p=a.play();if(p&&p.catch)p.catch(function(){});}}else if(!a.paused){a.pause();}}}
function seek(t){var shown=false;for(var i=0;i<scenes.length;i++){var sc=scenes[i],s=1000*(parseFloat(sc.getAttribute('data-start'))||0),d=1000*(parseFloat(sc.getAttribute('data-duration'))||0),a=(t>=s&&t<s+d);sc.style.display=a?'flex':'none';if(a){shown=true;sc.style.setProperty('--t0',(s-t)+'ms');}}
if(!shown&&scenes.length){scenes[scenes.length-1].style.display='flex';}syncAudio(t);}
addEventListener('message',function(e){var m=e.data;if(!m)return;if(m.type==='hf-seek'){if(typeof m.playing==='boolean')playing=m.playing;seek(m.t|0);}});seek(0);})();</script>`;
}

/**
 * Compile a Scene-JSON document into HyperFrames HTML.
 *
 * The output is a standalone HyperFrames composition (root
 * `data-composition-id` + per-clip `data-start`/`data-duration` in seconds on
 * one deterministic timeline). `npx hyperframes render` renders it; the editor
 * preview drives the same document with `{ preview: true }`. Pass
 * `fragment: true` to get just the composition node.
 */
export function compile(doc: SceneDocument, options: CompileOptions = {}): string {
  const autoMs = options.autoDurationMs ?? DEFAULT_AUTO_DURATION_MS;
  const { width, height } = dimensions(doc.aspectRatio);

  let cursor = 0;
  const audioClips: string[] = [];
  const scenes = doc.scenes
    .map((scene, index) => {
      const duration = resolveDurationMs(scene, autoMs);
      const html = renderScene(scene, index, cursor, duration);
      // Narration audio rides a separate track (10) as its own clip, windowed
      // to the scene, per the HyperFrames audio-clip contract.
      const audioUrl = scene.params?.audioUrl;
      if (typeof audioUrl === "string" && audioUrl) {
        audioClips.push(
          `<audio class="clip" id="audio-${index}" src="${esc(audioUrl)}" preload="auto"
    data-start="${sec(cursor)}" data-duration="${sec(duration)}" data-track-index="10"></audio>`,
        );
      }
      cursor += duration;
      return html;
    })
    .join("\n");

  const total = cursor;
  const composition = `<div id="root" class="hf-composition" data-composition-id="main"
    data-duration="${sec(total)}" data-width="${width}" data-height="${height}"
    data-aspect="${esc(doc.aspectRatio)}" data-project="${esc(doc.id)}">
${scenes}
${audioClips.join("\n")}
  </div>`;

  if (options.fragment) return composition;

  // Preview-only: center + scale the fixed-pixel composition to fit the iframe.
  // Absolute + translate centering — the composition is larger than the
  // viewport, so grid/flex centering cannot center it (no free space in the
  // auto track); scale() alone leaves it hanging off the bottom-right.
  const doFit = options.fit || options.preview;
  const fitCss = doFit
    ? `html,body{height:100%;overflow:hidden}.hf-composition{position:absolute;top:50%;left:50%}`
    : "";
  const fitScript = doFit
    ? `<script>(function(){var c=document.querySelector('.hf-composition');if(!c)return;function f(){var s=Math.min(innerWidth/${width},innerHeight/${height});c.style.transform='translate(-50%,-50%) scale('+s+')';}addEventListener('resize',f);f();})();</script>`
    : "";
  const runtime = options.preview ? previewRuntime() : "";

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
${runtime}
</body>
</html>`;
}
