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

/**
 * Real renderer: writes the compiled composition to a temp project dir, runs
 * `hyperframes render` (headless Chrome + FFmpeg), uploads the video to
 * MinIO/S3, and yields a presigned URL. Requires ffmpeg + a Chrome the
 * hyperframes CLI can find (`npx hyperframes browser ensure` — baked into the
 * Docker image).
 */
export class HyperframesRenderEngine implements RenderEngine {
  constructor(private readonly config: RenderConfig) {}

  async *render(html: string, settings: RenderSettings): AsyncGenerator<RenderProgress> {
    const { mkdtemp, writeFile, stat, rm, readFile } = await import("node:fs/promises");
    const { tmpdir } = await import("node:os");
    const { join } = await import("node:path");
    const { spawn } = await import("node:child_process");

    const dir = await mkdtemp(join(tmpdir(), "vyakhya-render-"));
    try {
      await writeFile(join(dir, "index.html"), html, "utf8");
      const ext = settings.format === "webm" ? "webm" : "mp4";
      const outPath = join(dir, `out.${ext}`);
      const quality = settings.quality >= 80 ? "high" : settings.quality >= 40 ? "standard" : "draft";
      // bun's isolated installs create no node_modules/.bin shim, so resolve
      // the CLI entry directly instead of relying on `npx hyperframes`.
      const { createRequire } = await import("node:module");
      const cli = createRequire(import.meta.url).resolve("hyperframes/dist/cli.js");
      const args = [
        cli,
        "render",
        dir,
        "--output",
        outPath,
        "--fps",
        String(settings.fps),
        "--quality",
        quality,
        "--format",
        ext,
        "--quiet",
      ];
      if (settings.gpu) args.push("--gpu");
      if (settings.workers > 0) args.push("--workers", String(settings.workers));

      yield { status: "running", progress: 0.02 };

      const child = spawn(process.execPath, args, { stdio: ["ignore", "pipe", "pipe"] });
      let stderrTail = "";
      let ticks = 0;
      const lines: string[] = [];
      child.stdout.on("data", (d: Buffer) => lines.push(d.toString()));
      child.stderr.on("data", (d: Buffer) => {
        stderrTail = (stderrTail + d.toString()).slice(-4000);
      });
      const exit = new Promise<number>((resolve, reject) => {
        child.on("error", reject);
        child.on("close", (code) => resolve(code ?? 1));
      });

      // Coarse progress while the CLI runs (it reports via stdout, not machine-
      // readable): creep toward 0.9, then jump to 1.0 on completion.
      let code: number | undefined;
      const donePromise = exit.then((c) => (code = c));
      while (code === undefined) {
        await new Promise((r) => setTimeout(r, 1500));
        ticks += 1;
        if (code === undefined) {
          yield { status: "running", progress: Math.min(0.9, 0.02 + ticks * 0.03) };
        }
      }
      await donePromise;

      if (code !== 0) {
        throw new Error(
          `hyperframes render exited ${code}: ${stderrTail || lines.join("").slice(-2000)}`,
        );
      }
      const info = await stat(outPath).catch(() => null);
      if (!info || info.size === 0) {
        throw new Error("hyperframes render produced no output file");
      }

      yield { status: "running", progress: 0.95 };
      const outputUrl = await this.upload(await readFile(outPath), ext);
      yield { status: "done", progress: 1, outputUrl };
    } finally {
      await rm(dir, { recursive: true, force: true }).catch(() => {});
    }
  }

  /** Upload to MinIO/S3 and return a browser-reachable presigned GET URL. */
  private async upload(body: Buffer, ext: string): Promise<string> {
    const { S3Client, PutObjectCommand, GetObjectCommand, CreateBucketCommand, HeadBucketCommand } =
      await import("@aws-sdk/client-s3");
    const { getSignedUrl } = await import("@aws-sdk/s3-request-presigner");
    const cfg = this.config;
    const creds = {
      credentials: { accessKeyId: cfg.s3AccessKey, secretAccessKey: cfg.s3SecretKey },
      region: "us-east-1",
      forcePathStyle: true,
    };
    const internal = new S3Client({ ...creds, endpoint: cfg.s3Endpoint });
    const key = `renders/render-${Date.now()}.${ext}`;
    try {
      await internal.send(new HeadBucketCommand({ Bucket: cfg.s3Bucket }));
    } catch {
      await internal.send(new CreateBucketCommand({ Bucket: cfg.s3Bucket })).catch(() => {});
    }
    await internal.send(
      new PutObjectCommand({
        Bucket: cfg.s3Bucket,
        Key: key,
        Body: body,
        ContentType: ext === "webm" ? "video/webm" : "video/mp4",
      }),
    );
    // Sign against the PUBLIC endpoint — the browser can't resolve `minio:9000`.
    const publicClient = new S3Client({ ...creds, endpoint: cfg.s3PublicEndpoint });
    return getSignedUrl(publicClient, new GetObjectCommand({ Bucket: cfg.s3Bucket, Key: key }), {
      expiresIn: 7 * 24 * 3600,
    });
  }
}

export function createEngine(config: RenderConfig): RenderEngine {
  return config.engine === "hyperframes"
    ? new HyperframesRenderEngine(config)
    : new SimulatedRenderEngine(config.sampleOutputUrl);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
