// Fastify render service. Endpoints:
//   GET  /health          → liveness
//   POST /lint   { doc }   → compile + lint report (no render)
//   POST /render { doc, settings } → SSE stream of RenderProgress
//
// The Vyakhya backend calls /render and proxies its progress to the UI.

import { compile, type SceneDocument } from "@vyakhya/compiler";
import Fastify, { type FastifyInstance } from "fastify";

import { loadConfig, type RenderConfig } from "./config.js";
import { createEngine, type RenderSettings } from "./engine.js";
import { runHyperframeLint } from "./lint.js";
import { LintError, runRender } from "./pipeline.js";

interface RenderBody {
  doc: SceneDocument;
  settings: RenderSettings;
}

export function buildServer(config: RenderConfig = loadConfig()): FastifyInstance {
  const app = Fastify({ logger: false });
  const engine = createEngine(config);

  // API-key gate (skips /health). Disabled when RENDER_API_KEY is unset.
  app.addHook("onRequest", async (req, reply) => {
    if (!config.apiKey || req.url === "/health") return;
    const provided = req.headers["x-api-key"];
    if (provided !== config.apiKey) {
      await reply.code(401).send({ error: "Invalid or missing API key" });
    }
  });

  app.get("/health", async () => ({ status: "ok", engine: config.engine }));

  app.post<{ Body: { doc: SceneDocument } }>("/lint", async (req, reply) => {
    const { doc } = req.body ?? {};
    if (!doc) return reply.code(400).send({ error: "missing doc" });
    const html = compile(doc);
    return runHyperframeLint(html);
  });

  app.post<{ Body: RenderBody }>("/render", async (req, reply) => {
    const { doc, settings } = req.body ?? {};
    if (!doc || !settings) return reply.code(400).send({ error: "missing doc or settings" });

    reply.raw.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });

    const write = (event: unknown) => reply.raw.write(`data: ${JSON.stringify(event)}\n\n`);

    try {
      for await (const progress of runRender({ doc, settings }, engine)) {
        write(progress);
      }
    } catch (err) {
      if (err instanceof LintError) {
        write({ status: "error", progress: 0, error: err.message });
      } else {
        write({ status: "error", progress: 0, error: (err as Error).message });
      }
    } finally {
      reply.raw.end();
    }
    return reply;
  });

  return app;
}

async function main(): Promise<void> {
  const config = loadConfig();
  const app = buildServer(config);
  await app.listen({ port: config.port, host: config.host });
  // eslint-disable-next-line no-console
  console.log(`render service listening on http://${config.host}:${config.port} (engine=${config.engine})`);
}

// Run only when executed directly (not when imported by tests).
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    process.exit(1);
  });
}
