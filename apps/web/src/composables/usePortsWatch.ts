import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import { api } from '@/api/http'

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
}

/** Single shared poll — toast + panel must not each hit /api/ports. */
const POLL_MS = 12_000

const ports = ref<PortItem[]>([])
const error = ref('')
const loading = ref(false)
const updatedAt = ref(0)

let timer: ReturnType<typeof setInterval> | null = null
let subscribers = 0
let inFlight: Promise<void> | null = null

async function refreshPorts(opts?: { quiet?: boolean }) {
  if (inFlight) return inFlight
  if (!opts?.quiet) loading.value = true
  error.value = ''
  inFlight = (async () => {
    try {
      const data = await api<{ ports: PortItem[] }>('/api/ports')
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
  error: Ref<string>
  loading: Ref<boolean>
  updatedAt: Ref<number>
  refresh: (opts?: { quiet?: boolean }) => Promise<void>
  pollMs: number
} {
  let release: (() => void) | null = null
  onMounted(() => {
    release = retainPortsWatch()
  })
  onUnmounted(() => {
    release?.()
    release = null
  })

  return {
    ports,
    error,
    loading,
    updatedAt,
    refresh: refreshPorts,
    pollMs: POLL_MS,
  }
}
