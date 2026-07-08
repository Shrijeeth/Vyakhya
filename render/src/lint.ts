// runHyperframeLint — the gate that rejects bad / non-seek-safe HTML before a
// costly render. Static checks over the compiled composition.

export interface LintResult {
  ok: boolean;
  errors: string[];
  warnings: string[];
}

const CLIP_RE = /<section[^>]*class="clip[^"]*"[^>]*>/g;
const START_RE = /data-start="([\d.]+)"/g;
const DURATION_RE = /data-duration="([\d.]+)"/g;

export function runHyperframeLint(html: string): LintResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!html || typeof html !== "string") {
    return { ok: false, errors: ["empty or non-string html"], warnings };
  }
  if (!html.includes("data-composition-id")) {
    errors.push("missing composition root (data-composition-id)");
  }

  const clips = html.match(CLIP_RE) ?? [];
  if (clips.length === 0) {
    errors.push("composition has no clips");
  }

  // Every clip needs seek-safe timing.
  for (const clip of clips) {
    if (!/data-start="/.test(clip)) errors.push("clip missing data-start");
    if (!/data-duration="/.test(clip)) errors.push("clip missing data-duration");
  }

  // Durations must be positive.
  for (const m of html.matchAll(DURATION_RE)) {
    if (Number(m[1]) <= 0) errors.push(`non-positive duration: ${m[1]}`);
  }

  // Clips should be laid out on a monotonic timeline.
  const starts = [...html.matchAll(START_RE)].map((m) => Number(m[1]));
  for (let i = 1; i < starts.length; i++) {
    if (starts[i]! < starts[i - 1]!) {
      warnings.push("clip start times are not monotonic");
      break;
    }
  }

  // Non-determinism / non-seek-safe hazards.
  if (/\bMath\.random\b/.test(html)) errors.push("Math.random() breaks determinism");
  if (/\bDate\.now\b|new Date\(\)/.test(html)) errors.push("wall-clock time breaks determinism");
  if (/<script\b/i.test(html)) warnings.push("inline <script> present — ensure it is seek-driven");

  return { ok: errors.length === 0, errors, warnings };
}
