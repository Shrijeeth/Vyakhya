import type { SceneDocument } from "@vyakhya/compiler";
import { describe, expect, it } from "vitest";

import { SimulatedRenderEngine, type RenderSettings } from "./engine.js";
import { runHyperframeLint } from "./lint.js";
import { buildServer } from "./server.js";
import { LintError, runRender } from "./pipeline.js";

const doc: SceneDocument = {
  id: "p1",
  title: "Demo",
  aspectRatio: "16:9",
  scenes: [
    { id: "s1", index: 1, narration: "hi", visualType: "title.card", params: { title: "Hi" }, durationMs: 4000 },
  ],
};

const settings: RenderSettings = {
  fps: 30,
  width: 1920,
  height: 1080,
  quality: 82,
  format: "mp4",
  codec: "h264",
  gpu: true,
  workers: 4,
  audioMasterDb: 0,
  audioNarrationDb: -2,
  audioMusicDb: -14,
};

describe("runHyperframeLint", () => {
  it("passes valid compiled HTML", () => {
    const html =
      '<div data-composition-id="main"><section class="clip" data-start="0" data-duration="4"></section></div>';
    expect(runHyperframeLint(html).ok).toBe(true);
  });

  it("fails when the composition root is missing", () => {
    expect(runHyperframeLint("<div></div>").ok).toBe(false);
  });

  it("fails on non-positive durations and non-determinism", () => {
    const bad =
      '<div data-composition-id="main"><section class="clip" data-start="0" data-duration="0"></section><script>Math.random()</script></div>';
    const res = runHyperframeLint(bad);
    expect(res.ok).toBe(false);
    expect(res.errors.some((e) => e.includes("duration"))).toBe(true);
    expect(res.errors.some((e) => e.includes("determinism"))).toBe(true);
  });
});

describe("runRender", () => {
  it("streams progress to a done event", async () => {
    const engine = new SimulatedRenderEngine("http://x/out.mp4");
    const events = [];
    for await (const p of runRender({ doc, settings }, engine)) events.push(p);
    expect(events[0]?.status).toBe("running");
    expect(events.at(-1)?.status).toBe("done");
    expect(events.at(-1)?.outputUrl).toBe("http://x/out.mp4");
  });

  it("throws LintError before rendering an empty document", async () => {
    const engine = new SimulatedRenderEngine("http://x/out.mp4");
    const emptyDoc: SceneDocument = { ...doc, scenes: [] };
    await expect(async () => {
      for await (const _ of runRender({ doc: emptyDoc, settings }, engine)) void _;
    }).rejects.toBeInstanceOf(LintError);
  });
});

describe("server", () => {
  it("GET /health reports the engine", async () => {
    const app = buildServer({ port: 0, host: "127.0.0.1", engine: "simulated", sampleOutputUrl: "http://x/o.mp4", apiKey: "" });
    const res = await app.inject({ method: "GET", url: "/health" });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ status: "ok", engine: "simulated" });
    await app.close();
  });

  it("POST /lint compiles and reports", async () => {
    const app = buildServer();
    const res = await app.inject({ method: "POST", url: "/lint", payload: { doc } });
    expect(res.statusCode).toBe(200);
    expect(res.json().ok).toBe(true);
    await app.close();
  });

  it("POST /render streams SSE ending in done", async () => {
    const app = buildServer({ port: 0, host: "127.0.0.1", engine: "simulated", sampleOutputUrl: "http://x/o.mp4", apiKey: "" });
    const res = await app.inject({ method: "POST", url: "/render", payload: { doc, settings } });
    expect(res.statusCode).toBe(200);
    expect(res.body).toContain('"status":"done"');
    expect(res.body).toContain("http://x/o.mp4");
    await app.close();
  });
});

describe("api-key auth", () => {
  const cfg = {
    port: 0,
    host: "127.0.0.1",
    engine: "simulated" as const,
    sampleOutputUrl: "http://x/o.mp4",
    apiKey: "secret",
  };

  it("rejects /lint without the key", async () => {
    const app = buildServer(cfg);
    const res = await app.inject({ method: "POST", url: "/lint", payload: { doc } });
    expect(res.statusCode).toBe(401);
    await app.close();
  });

  it("accepts /lint with the key", async () => {
    const app = buildServer(cfg);
    const res = await app.inject({
      method: "POST",
      url: "/lint",
      headers: { "x-api-key": "secret" },
      payload: { doc },
    });
    expect(res.statusCode).toBe(200);
    await app.close();
  });

  it("leaves /health open", async () => {
    const app = buildServer(cfg);
    const res = await app.inject({ method: "GET", url: "/health" });
    expect(res.statusCode).toBe(200);
    await app.close();
  });
});
