import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // ── Repository Service (port 8001) ────────────────────────────────────
      // GitHub integration routes
      '/api/v1/github': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      // Org-scoped GitHub routes
      '/api/v1/organizations/': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        // Only proxy github/* and repositories routes to 8001
        // We use a rewrite condition via a bypass function
        bypass(req) {
          const url = req.url ?? '';
          const isRepoService =
            url.includes('/github') || url.includes('/repositories');
          if (!isRepoService) {
            // Let Vite fall through to the next proxy rule
            return false as unknown as string;
          }
          return undefined; // proxy it to 8001
        },
      },
      // Standalone repository routes
      '/api/v1/repositories': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      // ── API Service (port 8000) — catch-all ───────────────────────────────
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
