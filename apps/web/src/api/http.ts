export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) {
    const raw = await res.text()
    let detail: unknown = raw
    try {
      detail = raw ? JSON.parse(raw) : raw
    } catch {
      detail = raw
    }
    const msg =
      typeof detail === 'string'
        ? detail
        : JSON.stringify((detail as { detail?: unknown }).detail || detail)
    throw new Error(msg || res.statusText)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export type StreamEnvelope = {
  v: number
  event_id: string
  run_id: string
  ts: string
  type: string
  seq: number
  payload: Record<string, unknown>
}

export type StreamConnectionState = 'connecting' | 'live' | 'reconnecting' | 'closed'

/** Browser EventSource auto-retries; stop after this many error cycles. */
const MAX_STREAM_RECONNECT_ATTEMPTS = 5

export function subscribeRun(
  runId: string,
  lastEventId: string | null,
  onEvent: (event: StreamEnvelope) => void,
  onDone?: () => void,
  onConnection?: (state: StreamConnectionState) => void,
): () => void {
  const url = new URL(`/api/runs/${runId}/events`, window.location.origin)
  if (lastEventId) url.searchParams.set('last_event_id', lastEventId)
  const es = new EventSource(url.toString())
  let settled = false
  let intentionalClose = false
  let reconnectAttempts = 0
  onConnection?.('connecting')

  const markLive = () => {
    if (settled || intentionalClose) return
    reconnectAttempts = 0
    onConnection?.('live')
  }

  es.onopen = () => {
    if (!settled && !intentionalClose) markLive()
  }

  es.onmessage = (ev) => {
    if (settled || intentionalClose) return
    markLive()
    let data: StreamEnvelope
    try {
      data = JSON.parse(ev.data) as StreamEnvelope
    } catch {
      return
    }
    onEvent(data)
    if (['run.completed', 'run.failed', 'run.cancelled'].includes(data.type)) {
      settled = true
      intentionalClose = true
      es.close()
      onConnection?.('closed')
      onDone?.()
    }
  }

  es.onerror = () => {
    // Let the browser auto-retry with Last-Event-ID while CONNECTING,
    // but give up after MAX_STREAM_RECONNECT_ATTEMPTS so the UI can show disconnected.
    if (settled || intentionalClose) return
    reconnectAttempts += 1
    if (reconnectAttempts > MAX_STREAM_RECONNECT_ATTEMPTS) {
      intentionalClose = true
      settled = true
      es.close()
      onConnection?.('closed')
      return
    }
    onConnection?.('reconnecting')
  }

  return () => {
    intentionalClose = true
    settled = true
    es.close()
    // Do not emit 'closed' on intentional teardown — attachRun/detachRun own that.
  }
}
