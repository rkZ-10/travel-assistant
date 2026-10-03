import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// `npm run dev` serves on :5173 and proxies the agent backend (`travel-agent web` on :8765).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
      "/api": "http://127.0.0.1:8765",
    },
  },
});
