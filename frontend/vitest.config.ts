import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

// Dedicated Vitest config (takes precedence over vite.config.ts) so the
// TanStack Start / Nitro plugins don't load during unit tests.
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    globals: true,
  },
});
