// Scene-JSON types — the contract crossing Python ⇄ browser ⇄ render worker.
//
// These mirror the backend Pydantic definition in
// `backend/vyakhya/agents/schema.py` (destined to be generated from its JSON
// Schema; hand-kept in sync for now). Field names are the camelCase wire form.

export type VisualType =
  | "title.card"
  | "bullet.reveal"
  | "figure.callout"
  | "equation.build"
  | "dataviz.bar"
  | "diagram.attention"
  | "comparison.split"
  | "kinetic.type";

export type CaptionStyle = "none" | "minimal" | "bold";
export type SceneTransition = "cut" | "fade" | "slide" | "wipe";
export type AspectRatio = "16:9" | "9:16" | "1:1";

export interface SceneCitation {
  id: string;
  label: string;
  sourceSpan: string;
}

export interface SceneNode {
  id: string;
  index: number;
  narration: string;
  visualType: VisualType;
  params: Record<string, unknown>;
  captionStyle?: CaptionStyle;
  transition?: SceneTransition;
  /** number of ms, or the string "auto" */
  durationMs?: number | "auto";
  citations?: SceneCitation[];
}

export interface SceneDocument {
  id: string;
  title: string;
  aspectRatio: AspectRatio;
  scenes: SceneNode[];
}

// ── Param shapes per visual.type (see docs/api.md) ────────────────────────────
export interface TitleCardParams {
  title?: string;
  subtitle?: string;
}
export interface BulletRevealParams {
  bullets?: string[];
}
export interface FigureCalloutParams {
  caption?: string;
  figureRef?: string;
}
export interface EquationBuildParams {
  latex?: string;
}
export interface DatavizBarParams {
  series?: { label: string; value: number }[];
}
export interface DiagramAttentionParams {
  tokens?: string[];
}
export interface ComparisonSplitParams {
  left?: string;
  right?: string;
}
export interface KineticTypeParams {
  text?: string;
}

export interface CompileOptions {
  /** Fallback duration (ms) for scenes with `durationMs: "auto"`. */
  autoDurationMs?: number;
  /** Emit a full HTML document (default) or just the composition fragment. */
  fragment?: boolean;
  /**
   * Preview-only: scale the fixed-pixel composition to fit the viewport
   * (and center it) so it's visible in a small iframe. Not for the render path.
   */
  fit?: boolean;
}
