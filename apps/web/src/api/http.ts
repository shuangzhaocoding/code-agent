export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly detail: unknown

  constructor(status: number, detail: unknown, statusText = '') {
    const parsed = extractApiDetail(detail)
    super(parsed.message || parsed.code || statusText || `HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.code = parsed.code
    this.detail = detail
  }
}

/** Unwrap FastAPI `{ detail }` and pull `code` / `message` when present. */
export function extractApiDetail(detail: unknown): { code?: string; message?: string; raw: unknown } {
  let body: unknown = detail
  if (body && typeof body === 'object' && 'detail' in (body as object)) {
    body = (body as { detail: unknown }).detail
  }
  if (typeof body === 'string') {
    const text = body
    try {
      const nested = JSON.parse(text) as unknown
      if (nested && typeof nested === 'object') body = nested
      else return { message: text, raw: text }
    } catch {
      return { message: text, raw: text }
    }
  }
  if (body && typeof body === 'object') {
    const o = body as Record<string, unknown>
    const code = typeof o.code === 'string' ? o.code : undefined
    const message = typeof o.message === 'string' ? o.message : undefined
    return { code, message, raw: body }
  }
  return { raw: body }
}

export function getErrorCode(err: unknown): string | undefined {
  if (err instanceof ApiError) return err.code
  const msg = err instanceof Error ? err.message : String(err)
  if (!msg) return undefined
  try {
    const parsed = extractApiDetail(JSON.parse(msg))
    return parsed.code
  } catch {
    const m = msg.match(/"code"\s*:\s*"([^"]+)"/)
    return m?.[1]
  }
}

export function isPathNotFoundError(err: unknown): boolean {
  return getErrorCode(err) === 'path.not_found' || (err instanceof Error && err.message.includes('path.not_found'))
}

export function isFileTooLargeError(err: unknown): boolean {
  const code = getErrorCode(err)
  if (code === 'file.too_large') return true
  const msg = err instanceof Error ? err.message : String(err)
  return msg.includes('file.too_large') || /File exceeds \d+ bytes/i.test(msg)
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    credentials: 'include',
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
    const err = new ApiError(res.status, detail, res.statusText)
    if (res.status === 401 && getErrorCode(err) === 'auth.required') {
      window.dispatchEvent(new CustomEvent('ca-auth-required'))
    }
    throw err
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export async function fetchAuthStatus(): Promise<{ required: boolean; unlocked: boolean }> {
  return api('/api/auth/status')
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

export type WorkspaceFsEvent = {
  type: string
  workspace_id?: string
  paths?: string[]
  kinds?: string[]
  truncated?: boolean
  reason?: string
  mode?: string
  message?: string
  hint_code?: string
  install_attempted?: boolean
  install_ok?: boolean
  phase?: string
}

/** Subscribe to workspace filesystem change events (local watch / SSH poll). */
export function subscribeWorkspaceEvents(
  workspaceId: string,
  onEvent: (event: WorkspaceFsEvent) => void,
): () => void {
  const url = new URL(`/api/workspaces/${workspaceId}/events`, window.location.origin)
  const es = new EventSource(url.toString())
  let intentionalClose = false

  es.onmessage = (ev) => {
    if (intentionalClose) return
    try {
      const data = JSON.parse(ev.data) as WorkspaceFsEvent
      onEvent(data)
    } catch {
      /* ignore malformed frames */
    }
  }

  return () => {
    intentionalClose = true
    es.close()
  }
}
