import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Where /api is forwarded: SATYACHECK_BACKEND from the shell or web/.env.local, e.g.
  //   SATYACHECK_BACKEND=https://xyz.trycloudflare.com
  // The browser only ever talks to this dev server, so the backend's CORS list is not
  // involved. changeOrigin rewrites Host to the target's, which a Cloudflare tunnel
  // needs to route the request at all; ws forwards the WebSocket upgrades too
  // (/api/ws/live, /api/ws/guardian — see docs/LIVE_FEED.md).
  const backend =
    loadEnv(mode, import.meta.dirname, '').SATYACHECK_BACKEND || 'http://localhost:8000'

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname, './src'),
      },
    },
    server: {
      proxy: {
        '/api': { target: backend, changeOrigin: true, ws: true },
      },
    },
  }
})
