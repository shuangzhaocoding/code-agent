<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import { currentTheme, type Theme } from '@/theme'
import AppIcon from '@/components/AppIcon.vue'

const store = useAppStore()

interface TermEntry {
  id: string
  title: string
  alive: boolean
  term: Terminal | null
  fit: FitAddon | null
  ws: WebSocket | null
  observer: ResizeObserver | null
  el: HTMLDivElement | null   // dedicated DOM node per terminal
}

const tabs = reactive<TermEntry[]>([])
const activeId = ref<string | null>(null)
const sideWidth = ref(180)

/* ---- rename ---- */
const renamingId = ref<string | null>(null)
const renameVal = ref('')

function startRename(tab: TermEntry) {
  renamingId.value = tab.id
  renameVal.value = tab.title
  nextTick(() => {
    const inp = document.querySelector('.rename-input') as HTMLInputElement | null
    inp?.focus()
    inp?.select()
  })
}
async function commitRename(tab: TermEntry) {
  const v = renameVal.value.trim()
  if (v && v !== tab.title) {
    tab.title = v
    await api(`/api/terminals/${tab.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: v }),
    }).catch(() => {})
  }
  renamingId.value = null
}
// Container that holds all per-terminal divs
const hostsEl = ref<HTMLDivElement | null>(null)

const lightTheme = {
  background: '#ffffff', foreground: '#1f2937', cursor: '#2563eb',
  cursorAccent: '#ffffff', selectionBackground: '#bfdbfe',
  black: '#1f2937', red: '#dc2626', green: '#059669', yellow: '#d97706',
  blue: '#2563eb', magenta: '#7c3aed', cyan: '#0891b2', white: '#e5e7eb',
  brightBlack: '#6b7280', brightRed: '#ef4444', brightGreen: '#10b981',
  brightYellow: '#f59e0b', brightBlue: '#3b82f6', brightMagenta: '#8b5cf6',
  brightCyan: '#06b6d4', brightWhite: '#111827',
}
const darkTheme = {
  background: '#0f1115', foreground: '#e5e7eb', cursor: '#60a5fa',
  cursorAccent: '#0f1115', selectionBackground: '#1e3a5f',
  black: '#0f1115', red: '#f87171', green: '#34d399', yellow: '#fbbf24',
  blue: '#60a5fa', magenta: '#c084fc', cyan: '#22d3ee', white: '#d1d5db',
  brightBlack: '#6b7280', brightRed: '#fca5a5', brightGreen: '#6ee7b7',
  brightYellow: '#fde68a', brightBlue: '#93c5fd', brightMagenta: '#e9d5ff',
  brightCyan: '#67e8f9', brightWhite: '#f9fafb',
}

function termTheme(t: Theme) {
  return t === 'dark' ? darkTheme : lightTheme
}

/**
 * Create the xterm + fit for a new entry, attach it to its own <div>,
 * and append that div into the shared hosts container (hidden by default).
 */
function createAndMount(entry: TermEntry) {
  if (!hostsEl.value) return
  const div = document.createElement('div')
  div.className = 'term-instance'
  div.style.display = 'none'
  hostsEl.value.appendChild(div)
  entry.el = div

  const term = new Terminal({
    fontFamily: 'IBM Plex Mono, ui-monospace, monospace',
    fontSize: 13,
    lineHeight: 1.25,
    theme: termTheme(currentTheme()),
    convertEol: true,
    allowProposedApi: false,
    drawBoldTextInBrightColors: true,
  })
  const fit = new FitAddon()
  term.loadAddon(fit)
  term.open(div)
  fit.fit()

  const observer = new ResizeObserver(() => {
    fit.fit()
    if (entry.ws?.readyState === WebSocket.OPEN) {
      entry.ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
    }
  })
  observer.observe(div)

  term.onData((data) => {
    if (entry.ws?.readyState === WebSocket.OPEN) {
      entry.ws.send(JSON.stringify({ type: 'input', data }))
    }
  })

  entry.term = term
  entry.fit = fit
  entry.observer = observer
}

async function connectEntry(entry: TermEntry) {
  if (!store.workspaceId) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const socket = new WebSocket(`${proto}://${location.host}/api/terminals/${entry.id}/ws`)
  socket.binaryType = 'arraybuffer'
  entry.ws = socket
  socket.onopen = () => {
    entry.alive = true
    if (entry.fit && entry.term) {
      entry.fit.fit()
      socket.send(JSON.stringify({ type: 'resize', cols: entry.term.cols, rows: entry.term.rows }))
    }
  }
  socket.onmessage = (ev) => {
    if (typeof ev.data === 'string') return
    entry.term?.write(new Uint8Array(ev.data as ArrayBuffer))
  }
  socket.onclose = () => { entry.alive = false }
}

/** Show the target terminal's div, hide all others, then refit. */
function activateTab(id: string) {
  activeId.value = id
  for (const t of tabs) {
    if (t.el) t.el.style.display = t.id === id ? '' : 'none'
  }
  const entry = tabs.find((t) => t.id === id)
  if (!entry) return
  nextTick(() => {
    entry.fit?.fit()
    entry.term?.focus()
  })
}

async function addTerminal() {
  if (!store.workspaceId) return
  const row = await api<{ id: string; title: string }>('/api/terminals', {
    method: 'POST',
    body: JSON.stringify({ workspace_id: store.workspaceId, title: `Terminal ${tabs.length + 1}` }),
  })
  const entry: TermEntry = {
    id: row.id,
    title: row.title || `Terminal ${tabs.length + 1}`,
    alive: true,
    term: null, fit: null, ws: null, observer: null, el: null,
  }
  tabs.push(entry)
  await nextTick()          // hostsEl must be rendered
  createAndMount(entry)
  activateTab(entry.id)
  await connectEntry(entry)
}

async function removeTerminal(id: string) {
  const idx = tabs.findIndex((t) => t.id === id)
  if (idx < 0) return
  const entry = tabs[idx]
  entry.ws?.close()
  entry.observer?.disconnect()
  entry.term?.dispose()
  entry.el?.remove()
  try { await api(`/api/terminals/${id}`, { method: 'DELETE' }) } catch { /* ok */ }
  tabs.splice(idx, 1)
  if (activeId.value === id) {
    const next = tabs[idx] || tabs[idx - 1]
    if (next) activateTab(next.id)
    else activeId.value = null
  }
}

async function loadExisting() {
  if (!store.workspaceId) return
  const list = await api<{ id: string; title: string; alive: boolean }[]>(
    `/api/terminals?workspace_id=${store.workspaceId}`,
  )
  for (const row of list) {
    const entry: TermEntry = {
      id: row.id,
      title: row.title || `Terminal ${tabs.length + 1}`,
      alive: row.alive,
      term: null, fit: null, ws: null, observer: null, el: null,
    }
    tabs.push(entry)
  }
  if (tabs.length === 0) {
    await addTerminal()
    return
  }
  await nextTick()
  for (const entry of tabs) createAndMount(entry)
  activateTab(tabs[0].id)
  for (const entry of tabs) await connectEntry(entry)
}

function onTheme(e: Event) {
  const theme = termTheme((e as CustomEvent<Theme>).detail)
  for (const entry of tabs) {
    if (entry.term) entry.term.options.theme = theme
  }
}

function onDragStart(e: MouseEvent) {
  e.preventDefault()
  const startX = e.clientX
  const startW = sideWidth.value
  function onMove(ev: MouseEvent) {
    sideWidth.value = Math.max(100, Math.min(320, startW + (startX - ev.clientX)))
  }
  function onUp() {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

onMounted(async () => {
  window.addEventListener('ca-theme', onTheme as EventListener)
  await loadExisting()
})

watch(() => store.workspaceId, async () => {
  for (const entry of tabs) {
    entry.ws?.close()
    entry.observer?.disconnect()
    entry.term?.dispose()
    entry.el?.remove()
  }
  tabs.splice(0, tabs.length)
  activeId.value = null
  await loadExisting()
})

onBeforeUnmount(() => {
  window.removeEventListener('ca-theme', onTheme as EventListener)
  for (const entry of tabs) {
    entry.ws?.close()
    entry.observer?.disconnect()
    entry.term?.dispose()
    entry.el?.remove()
  }
})
</script>

<template>
  <div class="panel-shell term-panel">
    <!-- shared container; each terminal lives in its own child div -->
    <div ref="hostsEl" class="term-hosts" />
    <div class="term-divider" @mousedown="onDragStart" />
    <aside class="term-sidebar" :style="{ width: sideWidth + 'px' }">
      <div class="side-head">
        <span class="side-title">终端</span>
        <button type="button" class="side-btn" title="新建终端" @click="addTerminal">
          <AppIcon name="plus" :size="14" />
        </button>
      </div>
      <div class="side-list">
        <div
          v-for="tab in tabs"
          :key="tab.id"
          class="side-item"
          :class="{ active: tab.id === activeId }"
          @click="activateTab(tab.id)"
        >
          <AppIcon name="terminal" :size="14" />
          <input
            v-if="renamingId === tab.id"
            v-model="renameVal"
            class="rename-input"
            @blur="commitRename(tab)"
            @keydown.enter="commitRename(tab)"
            @keydown.escape="renamingId = null"
          />
          <span v-else class="side-item-name" @dblclick.stop="startRename(tab)">{{ tab.title }}</span>
          <button type="button" class="side-item-close" title="关闭终端" @click.stop="removeTerminal(tab.id)">
            <AppIcon name="close" :size="12" />
          </button>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.term-panel {
  display: flex;
  flex-direction: row;
  background: var(--bg-elevated);
}
.term-hosts {
  flex: 1;
  min-width: 0;
  min-height: 0;
  position: relative;
}
/* each child div injected by createAndMount() */
.term-hosts :deep(.term-instance) {
  position: absolute;
  inset: 0;
  padding: 8px;
}
.term-divider {
  flex-shrink: 0;
  width: 4px;
  cursor: col-resize;
  background: transparent;
  transition: background 0.15s;
}
.term-divider:hover,
.term-divider:active {
  background: var(--primary);
  opacity: 0.45;
}
.term-sidebar {
  flex-shrink: 0;
  min-width: 100px;
  max-width: 320px;
  display: flex;
  flex-direction: column;
  border-left: var(--border-width) solid var(--border);
  background: var(--bg);
}
.side-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: var(--border-width) solid var(--border);
}
.side-title {
  flex: 1;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}
.side-btn {
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.side-btn:hover { background: var(--bg-muted); color: var(--text-h); }
.side-list {
  flex: 1;
  overflow: auto;
  padding: 4px 6px;
}
.side-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text);
  font-size: 12.5px;
}
.side-item:hover { background: var(--bg-muted); }
.side-item.active { background: var(--primary-soft); color: var(--primary); }
.side-item-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rename-input {
  flex: 1;
  min-width: 0;
  font-size: 12.5px;
  padding: 1px 4px;
  border: 1px solid var(--primary);
  border-radius: 3px;
  background: var(--bg);
  color: var(--text);
  outline: none;
}
.side-item-close {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  opacity: 0;
}
.side-item:hover .side-item-close { opacity: 0.6; }
.side-item-close:hover { opacity: 1 !important; background: var(--bg-muted); color: var(--text); }
</style>
