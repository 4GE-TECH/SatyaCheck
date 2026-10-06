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
  const env = loadEnv(mode, import.meta.dirname, '')
  const backend = env.SATYACHECK_BACKEND || 'http://localhost:8000'

  // The live feed's ?token= is added here, by the dev server, from SATYACHECK_LIVE_TOKEN.
  // The feed carries call transcripts, so the token stays out of the page, its URL and
  // the browser. Listed before /api because the first matching prefix wins.
  const liveToken = env.SATYACHECK_LIVE_TOKEN
  const withLiveToken = (path: string) =>
    liveToken && !/[?&]token=/.test(path)
      ? `${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(liveToken)}`
      : path

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname, './src'),
      },
    },
    server: {
      proxy: {
        '/api/ws/live': { target: backend, changeOrigin: true, ws: true, rewrite: withLiveToken },
        '/api': { target: backend, changeOrigin: true, ws: true },
      },
    },
  }
})
