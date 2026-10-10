import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      // SATYACHECK_BACKEND points the dev server at a remote backend, e.g. a Cloudflare tunnel.
      // changeOrigin is needed for Cloudflare; ws for the screening and live-feed sockets.
      '/api': { target: process.env.SATYACHECK_BACKEND ?? 'http://localhost:8000', changeOrigin: true, ws: true },
    },
  },
  build: { target: 'es2022' },
});
