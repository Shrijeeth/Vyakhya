import { describe, expect, it } from "vitest";
import { compile, getCompositionDuration, resolveDurationMs } from "./compile.js";
import { registry } from "./registry.js";
import type { SceneDocument, VisualType } from "./types.js";

const doc: SceneDocument = {
  id: "p1",
  title: "Attention Is All You Need",
  aspectRatio: "16:9",
  scenes: [
    {
      id: "s1",
      index: 1,
      narration: "In 2017 a team at Google rewrote how machines read language.",
      visualType: "title.card",
      params: { title: "Attention Is All You Need", subtitle: "Vaswani et al., 2017" },
      captionStyle: "minimal",
      transition: "fade",
      durationMs: 6000,
    },
    {
      id: "s2",
      index: 2,
      narration: "Attention scores every pair of tokens.",
      visualType: "diagram.attention",
      params: { tokens: ["The", "cat", "sat"] },
      durationMs: "auto",
      captionStyle: "bold",
    },
  ],
};

describe("resolveDurationMs", () => {
  it("returns numeric durations as-is", () => {
    expect(resolveDurationMs({ ...doc.scenes[0]! })).toBe(6000);
  });
  it("falls back for auto/invalid", () => {
    expect(resolveDurationMs({ ...doc.scenes[1]! }, 5000)).toBe(5000);
    expect(resolveDurationMs({ ...doc.scenes[0]!, durationMs: -1 }, 5000)).toBe(5000);
  });
});

describe("getCompositionDuration", () => {
  it("sums resolved scene durations", () => {
    expect(getCompositionDuration(doc, 5000)).toBe(6000 + 5000);
  });
});

describe("compile", () => {
  it("emits a full document with a composition and one clip per scene", () => {
    const html = compile(doc);
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain('data-hf-composition');
    expect((html.match(/class="clip /g) ?? []).length).toBe(2);
    expect(html).toContain('data-width="1920"');
  });

  it("lays clips out on a sequential timeline", () => {
    const html = compile(doc, { autoDurationMs: 5000 });
    expect(html).toContain('data-start="0"');
    expect(html).toContain('data-start="6000"'); // second clip starts after the first
    expect(html).toContain('data-duration="11000"'); // composition total
  });

  it("escapes user content (no injection)", () => {
    const html = compile({
      ...doc,
      scenes: [
        {
          id: "x",
          index: 1,
          narration: "<script>alert(1)</script>",
          visualType: "title.card",
          params: { title: "<img src=x onerror=1>" },
          captionStyle: "minimal",
        },
      ],
    });
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).not.toContain("<img src=x");
    expect(html).toContain("&lt;script&gt;");
  });

  it("renders 9:16 dimensions", () => {
    expect(compile({ ...doc, aspectRatio: "9:16" })).toContain('data-width="1080"');
  });

  it("degrades gracefully on an unknown visual type", () => {
    const html = compile({
      ...doc,
      scenes: [
        { id: "u", index: 1, narration: "", visualType: "does.not.exist" as VisualType, params: {} },
      ],
    });
    expect(html).toContain("Unsupported visual");
  });

  it("supports fragment output", () => {
    const frag = compile(doc, { fragment: true });
    expect(frag.startsWith("<main")).toBe(true);
    expect(frag).not.toContain("<!doctype");
  });
});

describe("registry", () => {
  it("has a renderer for every visual type", () => {
    const types: VisualType[] = [
      "title.card",
      "bullet.reveal",
      "figure.callout",
      "equation.build",
      "dataviz.bar",
      "diagram.attention",
      "comparison.split",
      "kinetic.type",
    ];
    for (const t of types) expect(typeof registry[t]).toBe("function");
  });

  it("dataviz scales bars to the max value", () => {
    const html = registry["dataviz.bar"]({
      series: [
        { label: "A", value: 10 },
        { label: "B", value: 20 },
      ],
    });
    expect(html).toContain("--pct:50%");
    expect(html).toContain("--pct:100%");
  });
});
