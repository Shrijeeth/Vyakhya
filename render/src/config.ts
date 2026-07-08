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
  };
}
