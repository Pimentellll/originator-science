import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Build identity for the System check page: lets a screenshot name the exact frontend build.
const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string }
const sha = (() => {
  try {
    return execSync('git rev-parse --short=12 HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()
  } catch {
    return 'unknown'
  }
})()

// The MIRAGE API serves from its root (`/episodes`, `/benchmarks`, ...). The app talks to
// same-origin `/api/*`; this proxy strips the prefix and forwards to MIRAGE_API_PROXY, so the
// browser needs no CORS configuration.
//
// Authorised aggregate results (`/benchmarks`) need X-Mirage-Eval-Token. The token is read from
// the dev machine's MIRAGE_EVAL_TOKEN and attached HERE, server-side. It is never a VITE_ variable,
// so it cannot end up in the client bundle.
// 127.0.0.1, not localhost: Node can resolve localhost to ::1 while uvicorn listens on IPv4 only.
const target = process.env.MIRAGE_API_PROXY ?? 'http://127.0.0.1:8000'
const token = process.env.MIRAGE_EVAL_TOKEN

const proxy = {
  '/api': {
    target,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ''),
    configure: (p: { on: (ev: 'proxyReq', cb: (req: { setHeader: (k: string, v: string) => void }, incoming: { url?: string }) => void) => void }) => {
      if (!token) return
      p.on('proxyReq', (req, incoming) => {
        // `rewrite` has already stripped /api by the time this hook runs; accept either form.
        if (/^(\/api)?\/benchmarks(\/|$)/.test(incoming.url ?? '')) req.setHeader('X-Mirage-Eval-Token', token)
      })
    },
  },
}

export default defineConfig({
  plugins: [react()],
  define: { __MIRAGE_FRONTEND__: JSON.stringify({ version: pkg.version, sha }) },
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
