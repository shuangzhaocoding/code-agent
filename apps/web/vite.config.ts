import { fileURLToPath, URL } from 'node:url'
import type { ProxyOptions } from 'vite'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiPort = Number(process.env.CODE_AGENT_PORT || 4060)
const devPort = Number(process.env.CODE_AGENT_DEV_UI_PORT || 4061)
const terminalPort = Number(process.env.CODE_AGENT_TERMINAL_PORT || 4062)
const previewPort = Number(process.env.CODE_AGENT_PREVIEW_PORT || 4063)
const split = process.env.CODE_AGENT_RUNTIME_PROFILE === 'split'

function upstream(port: number): ProxyOptions {
  return {
    target: `http://127.0.0.1:${port}`,
    changeOrigin: true,
    ws: true,
  }
}

// More specific prefixes first — Vite matches in definition order.
const proxy: Record<string, ProxyOptions> = split
  ? {
      '/api/preview': upstream(previewPort),
      '/api/ports': upstream(previewPort),
      '/api/terminals': upstream(terminalPort),
      '/api': upstream(apiPort),
    }
  : {
      '/api': upstream(apiPort),
    }

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: devPort,
    strictPort: true,
    proxy,
  },
  optimizeDeps: {
    include: ['monaco-editor', 'dockview-vue'],
    exclude: ['monaco-editor/editor/editor.worker.js'],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/monaco-editor')) return 'monaco'
          if (id.includes('node_modules/dockview')) return 'dockview'
          if (id.includes('node_modules/@opentiny')) return 'opentiny'
          if (id.includes('node_modules/@xterm')) return 'xterm'
        },
      },
    },
  },
})
