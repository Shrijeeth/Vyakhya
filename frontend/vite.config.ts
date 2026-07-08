import { defineConfig } from "vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsConfigPaths from "vite-tsconfig-paths";

// Standard TanStack Start plugin stack. Replaces the Lovable sandbox-only
// @lovable.dev/vite-tanstack-config meta-plugin so the app builds anywhere.
// src/start.ts and src/server.ts are picked up by Start via convention.
export default defineConfig({
  plugins: [
    tsConfigPaths(),
    tailwindcss(),
    tanstackStart({ customViteReactPlugin: true }),
    viteReact(),
  ],
});
