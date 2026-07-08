// Render engine seam. `SimulatedRenderEngine` produces progress + a sample
// artifact with no Chrome/FFmpeg (dev + CI). `HyperframesRenderEngine` is where
// `@hyperframes/producer` (headless Chrome + FFmpeg → MP4) drops in behind the
// same async-generator contract.

import type { RenderConfig } from "./config.js";

export interface RenderSettings {
  fps: 24 | 30 | 60;
  width: number;
  height: number;
  quality: number;
  format: "mp4" | "webm";
  codec: "h264" | "h265" | "vp9" | "av1";
  gpu: boolean;
  workers: number;
  audioMasterDb: number;
  audioNarrationDb: number;
  audioMusicDb: number;
}

export interface RenderProgress {
  status: "running" | "done" | "error";
  progress: number; // 0..1
  outputUrl?: string;
  error?: string;
}

export interface RenderEngine {
  render(html: string, settings: RenderSettings): AsyncGenerator<RenderProgress>;
}

export class SimulatedRenderEngine implements RenderEngine {
  constructor(private readonly outputUrl: string) {}

  async *render(_html: string, _settings: RenderSettings): AsyncGenerator<RenderProgress> {
    let progress = 0;
    yield { status: "running", progress: 0 };
    while (progress < 1) {
      await sleep(200);
      progress = Math.min(1, progress + 0.1);
      if (progress < 1) yield { status: "running", progress: Number(progress.toFixed(2)) };
    }
    yield { status: "done", progress: 1, outputUrl: this.outputUrl };
  }
}

export class HyperframesRenderEngine implements RenderEngine {
  // eslint-disable-next-line require-yield
  async *render(_html: string, _settings: RenderSettings): AsyncGenerator<RenderProgress> {
    // Wire @hyperframes/producer here:
    //   const job = createRenderJob({ html, ...settings })
    //   for await (const p of executeRenderJob(job)) yield p
    //   upload MP4 to MinIO/S3, yield done with the object URL.
    throw new Error(
      "HyperframesRenderEngine not wired yet — set RENDER_ENGINE=simulated or install @hyperframes/producer.",
    );
  }
}

export function createEngine(config: RenderConfig): RenderEngine {
  return config.engine === "hyperframes"
    ? new HyperframesRenderEngine()
    : new SimulatedRenderEngine(config.sampleOutputUrl);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
