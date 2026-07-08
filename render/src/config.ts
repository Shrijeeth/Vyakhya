// Render service configuration (from env).

export interface RenderConfig {
  port: number;
  host: string;
  /** Which render engine to use. `simulated` needs no Chrome/FFmpeg. */
  engine: "simulated" | "hyperframes";
  /** Fallback URL used by the simulated engine as the produced artifact. */
  sampleOutputUrl: string;
  /** Shared API key gating /lint and /render. Empty → auth disabled (dev). */
  apiKey: string;
  /** Object storage for finished videos (hyperframes engine). */
  s3Endpoint: string;
  /** Endpoint reachable from the user's BROWSER (host of the presigned URL). */
  s3PublicEndpoint: string;
  s3AccessKey: string;
  s3SecretKey: string;
  s3Bucket: string;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): RenderConfig {
  return {
    port: Number(env.RENDER_PORT ?? 8080),
    host: env.RENDER_HOST ?? "0.0.0.0",
    engine: (env.RENDER_ENGINE as RenderConfig["engine"]) ?? "simulated",
    sampleOutputUrl:
      env.RENDER_SAMPLE_URL ??
      "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    apiKey: env.RENDER_API_KEY ?? "",
    s3Endpoint: env.S3_ENDPOINT ?? "http://localhost:9000",
    s3PublicEndpoint: env.S3_PUBLIC_ENDPOINT ?? "http://localhost:9000",
    s3AccessKey: env.S3_ACCESS_KEY ?? "vyakhya",
    s3SecretKey: env.S3_SECRET_KEY ?? "change-me",
    s3Bucket: env.S3_BUCKET ?? "vyakhya",
  };
}
