// Unit tests exercise the browser code paths — define a minimal `window` so the
// api layer's IS_BROWSER guard is true (node test environment has none).
if (typeof (globalThis as { window?: unknown }).window === "undefined") {
  (globalThis as { window?: unknown }).window = globalThis;
}
