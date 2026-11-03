import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'url'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
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
      // ── AI Service (port 8002) ────────────────────────────────────────────
      // Org-scoped conversation and code review routes
      '/api/v1/organizations/[0-9]+/conversations': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
      '/api/v1/organizations/[0-9]+/code-reviews': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
      // Standalone conversation, messages, stream, and agent-run routes
      '/api/v1/conversations': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
      '/api/v1/code-reviews': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
      '/api/v1/feature-plans': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
      '/api/v1/agent-runs': {
        target: 'http://localhost:8002',
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
