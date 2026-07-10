// Per-scene screenshots of a compiled composition — the eyes of the pipeline's
// design reviewer. Compiles the doc with the seekable preview runtime, loads it
// in headless Chromium, seeks into each scene (75% through, so entrances have
// settled), and captures a PNG per scene.

import { compile, resolveDurationMs, type SceneDocument } from "@vyakhya/compiler";

import type { RenderConfig } from "./config.js";

export interface SceneShot {
  index: number;
  sceneId: string;
  /** ms into the composition where the shot was taken */
  tMs: number;
  /** base64 PNG */
  png: string;
}

// Must cover the largest cut the pipeline produces (scene budget caps at 60);
// a silently truncated set means the reviewer never sees the tail scenes.
const MAX_SHOTS = 64;

function viewport(aspect: string): { width: number; height: number } {
  if (aspect === "9:16") return { width: 540, height: 960 };
  if (aspect === "1:1") return { width: 720, height: 720 };
  return { width: 960, height: 540 };
}

/**
 * Capture one screenshot per scene. Requires a Chromium the service can launch:
 * `HYPERFRAMES_BROWSER_PATH` (the render image sets it) or playwright-core's
 * own installed chromium.
 */
export async function captureScenes(
  doc: SceneDocument,
  config: RenderConfig,
): Promise<SceneShot[]> {
  const { chromium } = await import("playwright-core");

  // Preview build: seekable runtime + fit-to-viewport scaling.
  let html = compile(doc, { preview: true, autoDurationMs: 6000 });
  // Figure/audio URLs are minted for the browser (public endpoint); inside the
  // container only the internal endpoint resolves.
  if (config.s3PublicEndpoint !== config.s3Endpoint) {
    html = html.split(config.s3PublicEndpoint).join(config.s3Endpoint);
  }

  const executablePath = process.env.HYPERFRAMES_BROWSER_PATH || undefined;
  const browser = await chromium.launch({
    executablePath,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });
  try {
    const page = await browser.newPage({ viewport: viewport(doc.aspectRatio) });
    await page
      .setContent(html, { waitUntil: "networkidle", timeout: 15_000 })
      .catch(() => page.setContent(html, { waitUntil: "load", timeout: 15_000 }));

    const shots: SceneShot[] = [];
    let cursor = 0;
    for (let i = 0; i < doc.scenes.length; i++) {
      const scene = doc.scenes[i]!;
      const dur = resolveDurationMs(scene, 6000);
      if (shots.length < MAX_SHOTS) {
        const t = Math.round(cursor + Math.min(dur * 0.75, Math.max(dur - 50, 0)));
        // String form: the callback runs in the page, but this file compiles
        // against the node lib (no `window` type).
        await page.evaluate(`window.postMessage({ type: "hf-seek", t: ${t} }, "*")`);
        await page.waitForTimeout(80);
        const png = await page.screenshot({ type: "png" });
        shots.push({ index: i, sceneId: scene.id, tMs: t, png: png.toString("base64") });
      }
      cursor += dur;
    }
    return shots;
  } finally {
    await browser.close();
  }
}
