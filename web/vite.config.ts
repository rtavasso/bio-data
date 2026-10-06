/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `bio commons serve` listens on 8765 by default; the dev server proxies the API to it.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://127.0.0.1:8765", changeOrigin: false } } },
  test: { environment: "jsdom", globals: true },
});
