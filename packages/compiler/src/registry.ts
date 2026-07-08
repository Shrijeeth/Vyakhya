// Registry: one entry per `visual.type`. Each renderer takes the scene's params
// and returns the inner HTML for the stage. New visual = new registry entry.
// Deterministic (no randomness), seek-safe (static markup; motion is CSS driven
// by the composition timeline in compile.ts).

import type {
  BulletRevealParams,
  ComparisonSplitParams,
  DatavizBarParams,
  DiagramAttentionParams,
  EquationBuildParams,
  FigureCalloutParams,
  KineticTypeParams,
  TitleCardParams,
  VisualType,
} from "./types.js";
import { esc } from "./util.js";

export type VisualRenderer = (params: Record<string, unknown>) => string;

function titleCard(p: Record<string, unknown>): string {
  const { title, subtitle } = p as TitleCardParams;
  return `<div class="hf-title">
    <h1 class="hf-h1">${esc(title ?? "")}</h1>
    ${subtitle ? `<p class="hf-sub">${esc(subtitle)}</p>` : ""}
  </div>`;
}

function bulletReveal(p: Record<string, unknown>): string {
  const bullets = ((p as BulletRevealParams).bullets ?? []).filter(Boolean);
  const items = bullets
    .map(
      (b, i) =>
        `<li class="hf-bullet" style="--i:${i}">${esc(b)}</li>`,
    )
    .join("");
  return `<ul class="hf-bullets">${items}</ul>`;
}

function figureCallout(p: Record<string, unknown>): string {
  const { caption, figureRef } = p as FigureCalloutParams;
  return `<figure class="hf-figure">
    <div class="hf-figbox">${esc(figureRef ?? "Figure")}</div>
    ${caption ? `<figcaption class="hf-figcap">${esc(caption)}</figcaption>` : ""}
  </figure>`;
}

function equationBuild(p: Record<string, unknown>): string {
  // LaTeX is rendered by the HyperFrames math block at render time; here we emit
  // the source in a deterministic container.
  const latex = (p as EquationBuildParams).latex ?? "";
  return `<div class="hf-equation" data-latex="${esc(latex)}"><code>${esc(latex)}</code></div>`;
}

function datavizBar(p: Record<string, unknown>): string {
  const series = (p as DatavizBarParams).series ?? [];
  const max = series.reduce((m, s) => Math.max(m, Number(s?.value) || 0), 0) || 1;
  const bars = series
    .map((s, i) => {
      const pct = Math.round(((Number(s?.value) || 0) / max) * 100);
      return `<div class="hf-bar" style="--i:${i}">
        <div class="hf-bar-fill" style="--pct:${pct}%"></div>
        <span class="hf-bar-label">${esc(s?.label ?? "")}</span>
        <span class="hf-bar-value">${esc(s?.value ?? "")}</span>
      </div>`;
    })
    .join("");
  return `<div class="hf-dataviz">${bars}</div>`;
}

function diagramAttention(p: Record<string, unknown>): string {
  const tokens = (p as DiagramAttentionParams).tokens ?? [];
  const chips = tokens
    .map((t, i) => `<span class="hf-token" style="--i:${i}">${esc(t)}</span>`)
    .join("");
  return `<div class="hf-attention">${chips}</div>`;
}

function comparisonSplit(p: Record<string, unknown>): string {
  const { left, right } = p as ComparisonSplitParams;
  return `<div class="hf-compare">
    <div class="hf-compare-side hf-left">${esc(left ?? "")}</div>
    <div class="hf-compare-divider"></div>
    <div class="hf-compare-side hf-right">${esc(right ?? "")}</div>
  </div>`;
}

function kineticType(p: Record<string, unknown>): string {
  const text = (p as KineticTypeParams).text ?? "";
  return `<div class="hf-kinetic"><span class="hf-kinetic-word">${esc(text)}</span></div>`;
}

export const registry: Record<VisualType, VisualRenderer> = {
  "title.card": titleCard,
  "bullet.reveal": bulletReveal,
  "figure.callout": figureCallout,
  "equation.build": equationBuild,
  "dataviz.bar": datavizBar,
  "diagram.attention": diagramAttention,
  "comparison.split": comparisonSplit,
  "kinetic.type": kineticType,
};

export function hasVisual(type: string): type is VisualType {
  return type in registry;
}
