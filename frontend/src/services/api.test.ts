import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createProject,
  getAgentSequence,
  getRenderSettings,
  listProjects,
  subscribePipeline,
  visualTypeSchemas,
} from "./api";
import type { PipelineEvent } from "./types";

afterEach(() => {
  vi.useRealTimers();
});

describe("projects service (mock layer)", () => {
  it("lists seeded projects", async () => {
    const projects = await listProjects();
    expect(projects.length).toBeGreaterThan(0);
    expect(projects[0]).toHaveProperty("status");
  });

  it("creates a project in the generating state", async () => {
    const file = new File(["%PDF-1.4"], "My Great Paper.pdf", { type: "application/pdf" });
    const p = await createProject({
      file,
      audience: "student",
      aspectRatio: "16:9",
      language: "en",
      targetLengthMin: 3,
    });
    expect(p.title).toBe("My Great Paper");
    expect(p.sourcePaper).toBe("My Great Paper.pdf");
    expect(p.status).toBe("generating");
    expect(p.durationMs).toBe(0);
  });
});

describe("agent sequence", () => {
  it("runs ingestor → assembler with a verifier stage", () => {
    const seq = getAgentSequence();
    expect(seq).toHaveLength(8);
    expect(seq[0].id).toBe("ingestor");
    expect(seq.at(-1)?.id).toBe("assembler");
    expect(seq.map((a) => a.id)).toContain("verifier");
  });
});

describe("render settings", () => {
  it("returns sane defaults", async () => {
    const s = await getRenderSettings();
    expect([24, 30, 60]).toContain(s.fps);
    expect(s.width).toBeGreaterThan(0);
  });
});

describe("visualTypeSchemas", () => {
  it("has a schema for every visual type used by scenes", () => {
    expect(visualTypeSchemas["title.card"].fields.length).toBeGreaterThan(0);
    expect(visualTypeSchemas["dataviz.bar"]).toBeDefined();
  });
});

describe("subscribePipeline", () => {
  it("streams events and finishes with a done event", async () => {
    vi.useFakeTimers();
    const events: PipelineEvent[] = [];
    const unsub = subscribePipeline("p1", (e) => events.push(e));

    await vi.advanceTimersByTimeAsync(60_000);
    unsub();

    expect(events.length).toBeGreaterThan(0);
    expect(events.some((e) => e.type === "status")).toBe(true);
    expect(events.at(-1)?.type).toBe("done");
  });

  it("stops emitting after unsubscribe", async () => {
    vi.useFakeTimers();
    const events: PipelineEvent[] = [];
    const unsub = subscribePipeline("p1", (e) => events.push(e));
    unsub();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(events).toHaveLength(0);
  });
});
