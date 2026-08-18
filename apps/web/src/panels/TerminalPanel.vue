<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import { currentTheme, type Theme } from '@/theme'

const store = useAppStore()
const host = ref<HTMLDivElement | null>(null)
const status = ref('idle')
let term: Terminal | null = null
let fit: FitAddon | null = null
let ws: WebSocket | null = null
let terminalId: string | null = null
let observer: ResizeObserver | null = null

const lightTheme = {
  background: '#ffffff',
  foreground: '#1f2937',
  cursor: '#2563eb',
  cursorAccent: '#ffffff',
  selectionBackground: '#bfdbfe',
  black: '#1f2937',
  red: '#dc2626',
  green: '#059669',
  yellow: '#d97706',
  blue: '#2563eb',
  magenta: '#7c3aed',
  cyan: '#0891b2',
  white: '#e5e7eb',
  brightBlack: '#6b7280',
  brightRed: '#ef4444',
  brightGreen: '#10b981',
  brightYellow: '#f59e0b',
  brightBlue: '#3b82f6',
  brightMagenta: '#8b5cf6',
  brightCyan: '#06b6d4',
  brightWhite: '#111827',
}
const darkTheme = {
  background: '#0f1115',
  foreground: '#e5e7eb',
  cursor: '#60a5fa',
  cursorAccent: '#0f1115',
  selectionBackground: '#1e3a5f',
  black: '#0f1115',
  red: '#f87171',
  green: '#34d399',
  yellow: '#fbbf24',
  blue: '#60a5fa',
  magenta: '#c084fc',
  cyan: '#22d3ee',
  white: '#d1d5db',
  brightBlack: '#6b7280',
  brightRed: '#fca5a5',
  brightGreen: '#6ee7b7',
  brightYellow: '#fde68a',
  brightBlue: '#93c5fd',
  brightMagenta: '#e9d5ff',
  brightCyan: '#67e8f9',
  brightWhite: '#f9fafb',
}

function termTheme(t: Theme) {
  return t === 'dark' ? darkTheme : lightTheme
}

async function connect() {
  if (!store.workspaceId) return
  const list = await api<{ id: string; alive: boolean }[]>(`/api/terminals?workspace_id=${store.workspaceId}`)
  const existing = list.find((t) => t.alive) || list[0]
  const row =
    existing ||
    (await api<{ id: string }>('/api/terminals', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: store.workspaceId, title: 'Terminal' }),
    }))
  terminalId = row.id
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/api/terminals/${terminalId}/ws`)
  ws.binaryType = 'arraybuffer'
  ws.onopen = () => {
    status.value = 'connected'
    resize()
  }
  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') return
    term?.write(new Uint8Array(ev.data as ArrayBuffer))
  }
  ws.onclose = () => {
    status.value = 'disconnected'
  }
}

function resize() {
  fit?.fit()
  if (ws && ws.readyState === WebSocket.OPEN && term) {
    ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
  }
}

function onTheme(e: Event) {
  if (term) term.options.theme = termTheme((e as CustomEvent<Theme>).detail)
}

onMounted(async () => {
  term = new Terminal({
    fontFamily: 'IBM Plex Mono, ui-monospace, monospace',
    fontSize: 13,
    lineHeight: 1.25,
    theme: termTheme(currentTheme()),
    convertEol: true,
    allowProposedApi: false,
    drawBoldTextInBrightColors: true,
  })
  fit = new FitAddon()
  term.loadAddon(fit)
  if (host.value) term.open(host.value)
  fit.fit()
  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'input', data }))
    }
  })
  observer = new ResizeObserver(() => resize())
  if (host.value) observer.observe(host.value)
  window.addEventListener('ca-theme', onTheme as EventListener)
  await connect()
})

watch(
  () => store.workspaceId,
  async () => {
    ws?.close()
    term?.clear()
    await connect()
  },
)

onBeforeUnmount(() => {
  window.removeEventListener('ca-theme', onTheme as EventListener)
  observer?.disconnect()
  ws?.close()
  term?.dispose()
})
</script>

<template>
  <div class="panel-shell">
    <div ref="host" class="host" />
  </div>
</template>

<style scoped>
.host {
  flex: 1;
  min-height: 0;
  padding: 8px;
  background: var(--bg-elevated);
}
</style>
