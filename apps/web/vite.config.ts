import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
  server: {
    // Pinned and strict: the Google OAuth redirect URIs are registered against this origin.
    port: 5175,
    strictPort: true,
    // Same-origin in dev, as in production (the API serves the built app): one cookie, no CORS.
    proxy: { "/api": { target: "http://127.0.0.1:8300", changeOrigin: false } },
  },
})
