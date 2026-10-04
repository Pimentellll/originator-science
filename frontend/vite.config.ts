import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// The live backend is expected at MIRAGE_API_PROXY (default localhost:8000).
// LiveApiTransport talks to same-origin `/api/*`, so no CORS handling is needed in dev.
const apiProxy = process.env.MIRAGE_API_PROXY ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: apiProxy, changeOrigin: true } },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
