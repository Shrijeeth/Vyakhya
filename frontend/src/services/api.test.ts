import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  addConnection,
  compileScenePreview,
  createProject,
  getAgentSequence,
  getRenderSettings,
  listProjects,
  subscribeRenderJob,
  visualTypeSchemas,
} from "./api";
import type { Project, Scene } from "./types";

const project: Project = {
  id: "p1",
  title: "Paper",
  sourcePaper: "Author, 2024",
  status: "ready",
  durationMs: 1000,
  updatedAt: "2026-07-08T00:00:00Z",
  audience: "student",
  aspectRatio: "16:9",
  language: "en",
  ttsEnabled: true,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("HTTP endpoints", () => {
  it("listProjects GETs /api/projects", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([project]));
    const projects = await listProjects();
    expect(projects).toEqual([project]);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(String(fetchMock.mock.calls[0]![0])).toContain("/api/projects");
  });

  it("createProject POSTs multipart form data", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(project));
    const file = new File(["%PDF"], "My Paper.pdf", { type: "application/pdf" });
    await createProject({
      file,
      audience: "student",
      aspectRatio: "16:9",
      language: "en",
      targetLengthMin: 3,
      ttsEnabled: true,
    });
    const init = fetchMock.mock.calls[0]![1]!;
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("aspectRatio")).toBe("16:9");
  });

  it("addConnection sends the raw apiKey as JSON", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ ...project, id: "c1" }));
    await addConnection({ provider: "openai", model: "gpt-4o", apiKey: "sk-secret" });
    const init = fetchMock.mock.calls[0]![1]!;
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toMatchObject({
      provider: "openai",
      apiKey: "sk-secret",
    });
  });

  it("throws on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "nope" }, 500));
    await expect(getRenderSettings()).rejects.toThrow();
  });
});

describe("static client metadata", () => {
  it("agent sequence runs ingestor → assembler with a verifier stage", () => {
    const seq = getAgentSequence();
    expect(seq).toHaveLength(7);
    expect(seq[0].id).toBe("ingestor");
    expect(seq.at(-1)?.id).toBe("assembler");
    expect(seq.map((a) => a.id)).toContain("verifier");
  });

  it("visualTypeSchemas covers every visual", () => {
    expect(visualTypeSchemas["title.card"].fields.length).toBeGreaterThan(0);
    expect(visualTypeSchemas["dataviz.bar"]).toBeDefined();
  });
});

describe("compileScenePreview (client-side compiler)", () => {
  it("compiles a scene to HyperFrames HTML with no round-trip", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const scene: Scene = {
      id: "s1",
      index: 1,
      narration: "hello",
      visualType: "title.card",
      params: { title: "Hi" },
      captionStyle: "minimal",
      transition: "fade",
      durationMs: 6000,
      citations: [],
    };
    const html = await compileScenePreview(scene);
    expect(html).toContain("data-composition-id");
    expect(html).toContain("Hi");
    expect(fetchMock).not.toHaveBeenCalled(); // preview is local
  });
});

describe("subscribeRenderJob (SSE over fetch)", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("parses SSE frames into job events", async () => {
    const frames =
      'data: {"id":"r1","status":"running","progress":0}\n\n' +
      'data: {"id":"r1","status":"done","progress":1,"outputUrl":"http://x/o.mp4"}\n\n';
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frames));
        controller.close();
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status: 200 }));

    const events: { status: string; outputUrl?: string | null }[] = [];
    await new Promise<void>((resolve) => {
      subscribeRenderJob("r1", (job) => {
        events.push(job);
        if (job.status === "done") resolve();
      });
    });
    expect(events).toHaveLength(2);
    expect(events.at(-1)?.outputUrl).toBe("http://x/o.mp4");
  });
});
