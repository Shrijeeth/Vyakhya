// The render pipeline: Scene-JSON → compile → lint (gate) → engine → progress.

import { compile, type SceneDocument } from "@vyakhya/compiler";

import type { RenderEngine, RenderProgress, RenderSettings } from "./engine.js";
import { runHyperframeLint } from "./lint.js";

export interface RenderRequest {
  doc: SceneDocument;
  settings: RenderSettings;
}

export class LintError extends Error {
  constructor(public readonly errors: string[]) {
    super(`compiled HTML failed lint: ${errors.join("; ")}`);
    this.name = "LintError";
  }
}

/**
 * Run one render. Compiles the document, gates on lint, then streams engine
 * progress. Throws `LintError` before any (costly) render if the HTML is bad.
 */
export async function* runRender(
  req: RenderRequest,
  engine: RenderEngine,
): AsyncGenerator<RenderProgress> {
  const html = compile(req.doc, {
    autoDurationMs: 6000,
  });

  const lint = runHyperframeLint(html);
  if (!lint.ok) {
    throw new LintError(lint.errors);
  }

  yield* engine.render(html, req.settings);
}
