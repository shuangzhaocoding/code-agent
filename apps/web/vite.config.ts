import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiPort = Number(process.env.CODE_AGENT_PORT || 4060)
const devPort = Number(process.env.CODE_AGENT_DEV_UI_PORT || 4061)

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
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
        ws: true,
      },
    },
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
