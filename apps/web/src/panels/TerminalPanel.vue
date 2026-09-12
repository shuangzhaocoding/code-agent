<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import { currentTheme, type Theme } from '@/theme'
import AppIcon from '@/components/AppIcon.vue'
import ContextMenu, { type ContextMenuItem } from '@/components/ContextMenu.vue'
import { takeTerminalCwd, takeTerminalRun } from '@/utils/terminalOpen'
import {
  TERMINAL_MENTION_PATH,
  terminalSelectionRange,
} from '@/utils/terminalMention'

const { t } = useI18n()
const store = useAppStore()

interface TermEntry {
  id: string
  title: string
  alive: boolean
  term: Terminal | null
  fit: FitAddon | null
  ws: WebSocket | null
  observer: ResizeObserver | null
  el: HTMLDivElement | null
}

const tabs = reactive<TermEntry[]>([])
const activeId = ref<string | null>(null)
const sideWidth = ref(180)
const ctxMenu = ref<{ x: number; y: number } | null>(null)
const renamingId = ref<string | null>(null)
const renameVal = ref('')
const hostsEl = ref<HTMLDivElement | null>(null)

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
  background: '#121218', foreground: '#e5e7eb', cursor: '#60a5fa',
  cursorAccent: '#121218', selectionBackground: '#1e3a5f',
  black: '#121218', red: '#f87171', green: '#34d399', yellow: '#fbbf24',
  blue: '#60a5fa', magenta: '#c084fc', cyan: '#22d3ee', white: '#d1d5db',
  brightBlack: '#6b7280', brightRed: '#fca5a5', brightGreen: '#6ee7b7',
  brightYellow: '#fde68a', brightBlue: '#93c5fd', brightMagenta: '#e9d5ff',
  brightCyan: '#67e8f9', brightWhite: '#f9fafb',
}

function termTheme(theme: Theme) {
  const base = theme === 'dark' ? darkTheme : lightTheme
  if (typeof document === 'undefined') return base
  const bg = getComputedStyle(document.documentElement).getPropertyValue('--surface').trim()
  if (!bg) return base
  return { ...base, background: bg, cursorAccent: bg }
}

function activeEntry() {
  return tabs.find((row) => row.id === activeId.value) || null
}

function activeTerm() {
  return activeEntry()?.term || null
}

function selectionMention(term?: Terminal | null) {
  const entry = term ? tabs.find((row) => row.term === term) : activeEntry()
  const range = terminalSelectionRange(term || entry?.term || null)
  if (!range || !entry) return null
  return {
    name: entry.title || t('panels.terminal'),
    path: TERMINAL_MENTION_PATH,
    is_dir: false,
    lineStart: range.startLine,
    lineEnd: range.endLine,
    snippet: range.text,
  }
}

async function copySelection(term?: Terminal | null) {
  const target = term || activeTerm()
  const range = terminalSelectionRange(target)
  if (!range) return false
  const entry = term ? tabs.find((row) => row.term === term) : activeEntry()
  try {
    await navigator.clipboard.writeText(range.text)
    store.setTerminalCopyContext({
      text: range.text,
      startLine: range.startLine,
      endLine: range.endLine,
      title: entry?.title || t('panels.terminal'),
    })
    return true
  } catch {
    return false
  }
}

async function pasteClipboard(term?: Terminal | null) {
  const entry = term ? tabs.find((row) => row.term === term) : activeEntry()
  if (!entry?.term || entry.ws?.readyState !== WebSocket.OPEN) return
  try {
    const text = await navigator.clipboard.readText()
    if (!text) return
    entry.ws.send(JSON.stringify({ type: 'input', data: text }))
  } catch {
    /* clipboard denied */
  }
}

function addSelectionToChat(term?: Terminal | null) {
  const item = selectionMention(term)
  if (!item) return
  window.dispatchEvent(new Event('ca-focus-agent'))
  window.dispatchEvent(new CustomEvent('ca-add-chat-mention', { detail: item }))
}

const ctxMenuItems = computed((): ContextMenuItem[] => {
  const hasSel = Boolean(activeTerm()?.hasSelection())
  return [
    { id: 'copy', label: t('terminal.copy'), icon: 'copy', disabled: !hasSel },
    { id: 'paste', label: t('terminal.paste'), icon: 'paste' },
    { id: 'sep', separator: true },
    {
      id: 'add-selection',
      label: t('terminal.addSelectionToChat'),
      icon: 'chat-plus',
      disabled: !hasSel,
    },
  ]
})

async function onCtxSelect(id: string) {
  if (id === 'copy') {
    await copySelection()
    return
  }
  if (id === 'paste') {
    await pasteClipboard()
    return
  }
  if (id === 'add-selection') addSelectionToChat()
}

function createAndMount(entry: TermEntry) {
  if (!hostsEl.value) return
  const div = document.createElement('div')
  div.className = 'term-instance'
  div.style.display = 'none'
  hostsEl.value.appendChild(div)
  entry.el = div

  const term = new Terminal({
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    fontSize: 13,
    lineHeight: 1.25,
    theme: termTheme(currentTheme()),
    convertEol: true,
    allowProposedApi: false,
    drawBoldTextInBrightColors: true,
    rightClickSelectsWord: false,
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

  term.attachCustomKeyEventHandler((ev) => {
    if (ev.type !== 'keydown') return true
    const mod = ev.ctrlKey || ev.metaKey
    if (!mod) return true
    const key = ev.key.toLowerCase()
    if (key === 'c' && term.hasSelection()) {
      void copySelection(term)
      return false
    }
    if (key === 'v') {
      void pasteClipboard(term)
      return false
    }
    return true
  })

  term.onData((data) => {
    if (entry.ws?.readyState === WebSocket.OPEN) {
      entry.ws.send(JSON.stringify({ type: 'input', data }))
    }
  })

  div.addEventListener('contextmenu', (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (entry.id !== activeId.value) activateTab(entry.id)
    ctxMenu.value = { x: e.clientX, y: e.clientY }
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
  const opened = new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error('terminal timeout')), 8000)
    socket.onopen = () => {
      window.clearTimeout(timer)
      entry.alive = true
      if (entry.fit && entry.term) {
        entry.fit.fit()
        socket.send(JSON.stringify({ type: 'resize', cols: entry.term.cols, rows: entry.term.rows }))
      }
      resolve()
    }
    socket.onerror = () => {
      window.clearTimeout(timer)
      reject(new Error('terminal socket error'))
    }
  })
  socket.onmessage = (ev) => {
    if (typeof ev.data === 'string') return
    entry.term?.write(new Uint8Array(ev.data as ArrayBuffer))
  }
  socket.onclose = () => { entry.alive = false }
  try {
    await opened
  } catch {
    entry.alive = false
  }
}

function waitForSocket(entry: TermEntry, timeoutMs = 5000): Promise<void> {
  if (entry.ws?.readyState === WebSocket.OPEN) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const started = Date.now()
    const timer = window.setInterval(() => {
      if (entry.ws?.readyState === WebSocket.OPEN) {
        window.clearInterval(timer)
        resolve()
      } else if (Date.now() - started > timeoutMs) {
        window.clearInterval(timer)
        reject(new Error('terminal timeout'))
      }
    }, 30)
  })
}

function sendTerminalInput(entry: TermEntry, data: string) {
  if (entry.ws?.readyState !== WebSocket.OPEN) return false
  entry.ws.send(JSON.stringify({ type: 'input', data }))
  return true
}

function liveEntry(): TermEntry | null {
  const active = activeEntry()
  if (active?.alive && active.ws?.readyState === WebSocket.OPEN) return active
  return tabs.find((row) => row.alive && row.ws?.readyState === WebSocket.OPEN) || null
}

async function runQueuedCommand() {
  const queued = takeTerminalRun()
  if (!queued?.command) return
  let entry = liveEntry()
  if (!entry) {
    try {
      await addTerminal(queued.cwd)
    } catch {
      return
    }
    entry = activeEntry()
    if (!entry) return
    try {
      await waitForSocket(entry)
    } catch {
      return
    }
  }
  activateTab(entry.id)
  sendTerminalInput(entry, `${queued.command}\r`)
  entry.term?.focus()
}

function activateTab(id: string) {
  activeId.value = id
  for (const row of tabs) {
    if (row.el) row.el.style.display = row.id === id ? '' : 'none'
  }
  const entry = tabs.find((row) => row.id === id)
  if (!entry) return
  nextTick(() => {
    entry.fit?.fit()
    entry.term?.focus()
  })
}

async function addTerminal(cwd?: string) {
  if (!store.workspaceId) return
  const body: { workspace_id: string; title?: string; cwd?: string } = {
    workspace_id: store.workspaceId,
    title: cwd ? undefined : t('terminal.untitled', { n: tabs.length + 1 }),
  }
  if (cwd) body.cwd = cwd
  const row = await api<{ id: string; title: string }>('/api/terminals', {
    method: 'POST',
    body: JSON.stringify(body),
  })
  const entry: TermEntry = {
    id: row.id,
    title: row.title || t('terminal.untitled', { n: tabs.length + 1 }),
    alive: true,
    term: null, fit: null, ws: null, observer: null, el: null,
  }
  tabs.push(entry)
  await nextTick()
  createAndMount(entry)
  activateTab(entry.id)
  await connectEntry(entry)
}

async function flushQueuedTerminal() {
  const queued = takeTerminalCwd()
  if (queued === undefined) return
  try {
    await addTerminal(queued || undefined)
  } catch {
    /* ignore */
  }
}

async function removeTerminal(id: string) {
  const idx = tabs.findIndex((row) => row.id === id)
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
      title: row.title || t('terminal.untitled', { n: tabs.length + 1 }),
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

function onTerminalRun() {
  void runQueuedCommand()
}

onMounted(async () => {
  window.addEventListener('ca-theme', onTheme as EventListener)
  window.addEventListener('ca-terminal-cwd', flushQueuedTerminal)
  await loadExisting()
  await flushQueuedTerminal()
  window.addEventListener('ca-terminal-run', onTerminalRun)
  await runQueuedCommand()
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
  window.removeEventListener('ca-terminal-cwd', flushQueuedTerminal)
  window.removeEventListener('ca-terminal-run', onTerminalRun)
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
    <div ref="hostsEl" class="term-hosts" />
    <div class="term-divider" @mousedown="onDragStart" />
    <aside class="term-sidebar" :style="{ width: sideWidth + 'px' }">
      <div class="side-head">
        <span class="side-title">{{ t('terminal.title') }}</span>
        <button type="button" class="ghost-icon-btn" :title="t('terminal.new')" @click="addTerminal()">
          <AppIcon name="plus" :size="16" :stroke-width="1.75" />
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
          <AppIcon name="terminal" :size="16" :stroke-width="1.75" />
          <input
            v-if="renamingId === tab.id"
            v-model="renameVal"
            class="rename-input"
            @blur="commitRename(tab)"
            @keydown.enter="commitRename(tab)"
            @keydown.escape="renamingId = null"
          />
          <span v-else class="side-item-name" @dblclick.stop="startRename(tab)">{{ tab.title }}</span>
          <button
            type="button"
            class="ghost-icon-btn side-item-close"
            :title="t('terminal.close')"
            @click.stop="removeTerminal(tab.id)"
          >
            <AppIcon name="trash" :size="14" :stroke-width="1.75" />
          </button>
        </div>
      </div>
    </aside>
    <ContextMenu
      v-if="ctxMenu"
      :x="ctxMenu.x"
      :y="ctxMenu.y"
      :items="ctxMenuItems"
      @select="onCtxSelect"
      @close="ctxMenu = null"
    />
  </div>
</template>

<style scoped>
.term-panel {
  display: flex;
  flex-direction: row;
  background: var(--panel-bg);
}
.term-hosts {
  flex: 1;
  min-width: 0;
  min-height: 0;
  position: relative;
  background: var(--panel-bg);
}
/* each child div injected by createAndMount() */
.term-hosts :deep(.term-instance) {
  position: absolute;
  inset: 0;
  padding: 8px;
  background: var(--panel-bg);
}
.term-hosts :deep(.xterm),
.term-hosts :deep(.xterm-viewport) {
  background: transparent;
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
  background: var(--sidebar-bg);
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
  letter-spacing: 0.04em;
  color: var(--text-muted);
}
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
.side-item:hover { background: var(--code-bg); }
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
  opacity: 0;
  transition: opacity 0.15s ease;
}
.side-item:hover .side-item-close { opacity: var(--ghost-hover-opacity); }
.side-item-close:hover { opacity: 1 !important; }
</style>
