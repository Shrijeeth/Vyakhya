// Production web server for the TanStack Start build.
//
// `vite build` emits a bare SSR fetch handler (dist/server/server.js) plus the
// hashed client assets (dist/client/**) — but NO static file serving. In dev
// `vite` serves the assets; in production nothing does, so /assets/*.css and
// /favicon.png 404 and the page renders unstyled. This wrapper serves static
// files out of dist/client first, then delegates everything else to SSR.
import { join, normalize } from "node:path";

import ssr from "./dist/server/server.js";

const CLIENT_DIR = join(import.meta.dir, "dist", "client");
const PORT = Number(process.env.PORT ?? 3000);
// Content-hashed bundles never change → cache hard. Everything else at the root
// (favicon, robots, …) gets a short revalidating cache.
const IMMUTABLE = "public, max-age=31536000, immutable";
const SHORT = "public, max-age=3600";

async function staticResponse(pathname: string): Promise<Response | null> {
  if (pathname === "/") return null;
  // Block path traversal before touching the filesystem.
  const safe = normalize(pathname).replace(/^(\.\.(\/|\\|$))+/, "");
  const filePath = join(CLIENT_DIR, safe);
  if (!filePath.startsWith(CLIENT_DIR)) return null;
  const file = Bun.file(filePath);
  if (!(await file.exists())) return null;
  return new Response(file, {
    headers: {
      "cache-control": pathname.startsWith("/assets/") ? IMMUTABLE : SHORT,
    },
  });
}

Bun.serve({
  port: PORT,
  idleTimeout: 0, // keep SSE streams (pipeline/render) open
  async fetch(request) {
    const url = new URL(request.url);
    const asset = await staticResponse(decodeURIComponent(url.pathname));
    if (asset) return asset;
    return ssr.fetch(request, {}, {});
  },
});

// eslint-disable-next-line no-console
console.log(`web listening on :${PORT}`);
