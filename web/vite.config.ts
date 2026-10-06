/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `bio commons serve` listens on 8765 by default; the dev server proxies the API to it.
// Builds use relative asset URLs so one build serves any base path ("/" or "/c/<tenant>/"): the server
// rewrites index.html for its base and announces it in <meta name="colloquy-base"> (src/base.ts).
export default defineConfig(({ command }) => ({
  base: command === "build" ? "./" : "/",
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://127.0.0.1:8765", changeOrigin: false } } },
  test: { environment: "jsdom", globals: true },
}));
