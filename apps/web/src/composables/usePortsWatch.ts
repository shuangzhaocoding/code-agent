import { onMounted, onUnmounted, ref, watch, type Ref } from 'vue'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'

const SYSTEM_PORTS = new Set([22, 25, 53, 111, 123, 135, 139, 445, 631, 5353])
const HIGHLIGHT_TTL_MS = 60_000

export type PortItem = {
  port: number
  address: string
  pid: number | null
  process: string | null
  cmdline: string | null
  url: string
  preview_path: string
  connect_host?: string
  reachable?: boolean
  self?: boolean
  remote?: boolean
  workspace_id?: string
}

/** Single shared poll — toast + panel must not each hit /api/ports. */
const POLL_MS = 12_000

const ports = ref<PortItem[]>([])
const highlightedPorts = ref<Set<number>>(new Set())
const error = ref('')
const loading = ref(false)
const updatedAt = ref(0)
const activeWorkspaceId = ref<string | null>(null)

const highlightTimers = new Map<number, ReturnType<typeof setTimeout>>()

export function isInterestingPort(item: PortItem): boolean {
  if (item.self) return false
  if (SYSTEM_PORTS.has(item.port)) return false
  return true
}

export function markPortHighlighted(port: number, ttlMs = HIGHLIGHT_TTL_MS) {
  const next = new Set(highlightedPorts.value)
  next.add(port)
  highlightedPorts.value = next

  const prev = highlightTimers.get(port)
  if (prev) clearTimeout(prev)
  highlightTimers.set(
    port,
    setTimeout(() => {
      highlightTimers.delete(port)
      if (!highlightedPorts.value.has(port)) return
      const cleared = new Set(highlightedPorts.value)
      cleared.delete(port)
      highlightedPorts.value = cleared
    }, ttlMs),
  )
}

export function clearPortHighlighted(port: number) {
  const timer = highlightTimers.get(port)
  if (timer) {
    clearTimeout(timer)
    highlightTimers.delete(port)
  }
  if (!highlightedPorts.value.has(port)) return
  const next = new Set(highlightedPorts.value)
  next.delete(port)
  highlightedPorts.value = next
}

let timer: ReturnType<typeof setInterval> | null = null
let subscribers = 0
let inFlight: Promise<void> | null = null

async function refreshPorts(opts?: { quiet?: boolean }) {
  if (inFlight) return inFlight
  if (!opts?.quiet) loading.value = true
  error.value = ''
  inFlight = (async () => {
    try {
      const q = activeWorkspaceId.value ? `?workspace_id=${encodeURIComponent(activeWorkspaceId.value)}` : ''
      const data = await api<{ ports: PortItem[] }>(`/api/ports${q}`)
      ports.value = data.ports || []
      updatedAt.value = Date.now()
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
      inFlight = null
    }
  })()
  return inFlight
}

function startSharedTimer() {
  if (timer) return
  timer = setInterval(() => {
    void refreshPorts({ quiet: true })
  }, POLL_MS)
}

function stopSharedTimer() {
  if (!timer) return
  clearInterval(timer)
  timer = null
}

function retainPortsWatch() {
  subscribers += 1
  if (subscribers === 1) {
    void refreshPorts()
    startSharedTimer()
  }
  return () => {
    subscribers = Math.max(0, subscribers - 1)
    if (subscribers === 0) stopSharedTimer()
  }
}

/** Subscribe to the shared port list (one /api/ports poller for the whole app). */
export function usePortsWatch(): {
  ports: Ref<PortItem[]>
  highlightedPorts: Ref<Set<number>>
  error: Ref<string>
  loading: Ref<boolean>
  updatedAt: Ref<number>
  refresh: (opts?: { quiet?: boolean }) => Promise<void>
  pollMs: number
  markPortHighlighted: (port: number, ttlMs?: number) => void
  clearPortHighlighted: (port: number) => void
} {
  const store = useAppStore()
  let release: (() => void) | null = null
  let stopWatch: (() => void) | null = null

  onMounted(() => {
    activeWorkspaceId.value = store.workspaceId || null
    release = retainPortsWatch()
    stopWatch = watch(
      () => store.workspaceId,
      (id) => {
        const next = id || null
        if (next === activeWorkspaceId.value) return
        activeWorkspaceId.value = next
        highlightedPorts.value = new Set()
        void refreshPorts()
      },
    )
  })
  onUnmounted(() => {
    stopWatch?.()
    stopWatch = null
    release?.()
    release = null
  })

  return {
    ports,
    highlightedPorts,
    error,
    loading,
    updatedAt,
    refresh: refreshPorts,
    pollMs: POLL_MS,
    markPortHighlighted,
    clearPortHighlighted,
  }
}
