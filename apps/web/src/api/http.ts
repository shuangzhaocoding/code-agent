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

export function subscribeRun(
  runId: string,
  lastEventId: string | null,
  onEvent: (event: StreamEnvelope) => void,
  onDone?: () => void,
): () => void {
  const url = new URL(`/api/runs/${runId}/events`, window.location.origin)
  if (lastEventId) url.searchParams.set('last_event_id', lastEventId)
  const es = new EventSource(url.toString())
  es.onmessage = (ev) => {
    const data = JSON.parse(ev.data) as StreamEnvelope
    onEvent(data)
    if (['run.completed', 'run.failed', 'run.cancelled'].includes(data.type)) {
      es.close()
      onDone?.()
    }
  }
  es.onerror = () => {
    /* browser will retry using Last-Event-ID */
  }
  return () => es.close()
}
