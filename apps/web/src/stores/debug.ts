import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { api, getErrorCode } from '@/api/http'
import { useAppStore } from '@/stores/app'
import { t } from '@/i18n'
import { normalizeDebugPath } from '@/utils/debugPath'
import {
  BREAKPOINTS_FILE_REL,
  parseBreakpointsFile,
  pruneBreakpointsMap,
  readBreakpointsLocal,
  serializeBreakpointsFile,
  writeBreakpointsLocal,
} from '@/utils/debugBreakpointsStorage'

export type DebugBreakpoint = {
  line: number
  condition?: string
  hitCondition?: string
  logMessage?: string
}

export type DebugFrame = {
  id: number
  name: string
  line?: number
  column?: number
  path?: string | null
}

export type DebugVariable = {
  name: string
  value?: string
  type?: string
  variablesReference?: number
  namedVariables?: number
  indexedVariables?: number
  presentationHint?: { kind?: string; attributes?: string[]; visibility?: string }
}

export type DebugScope = {
  name: string
  variablesReference: number
  expensive?: boolean
}

export type DebugLaunchConfig = {
  name: string
  request?: string
  program?: string | null
  module?: string | null
  cwd?: string
  args?: string[]
  env?: Record<string, string>
  python?: string
  stopOnEntry?: boolean
  justMyCode?: boolean
}

export type DebugState = 'idle' | 'starting' | 'running' | 'paused' | 'stopped' | 'terminated' | 'error'

type WatchItem = { id: string; expression: string; value?: string; error?: string }

type StartOpts = {
  program?: string
  module?: string
  configName?: string | null
  stopOnEntry?: boolean
}

export type DebugSessionTab = {
  id: string
  title: string
  program: string | null
  module: string | null
  state: DebugState
  error: string | null
  frames: DebugFrame[]
  activeFrameId: number | null
  scopes: DebugScope[]
  variablesByRef: Record<number, DebugVariable[]>
  output: string[]
  consoleLines: { text: string; kind: 'in' | 'out' | 'err' | 'stdout' }[]
  currentPath: string | null
  currentLine: number | null
  stopReason: string | null
  busy: boolean
  lastStartOpts: StartOpts | null
}

let bpIdSeq = 1

function basename(path: string | null | undefined): string {
  if (!path) return 'debug'
  const parts = path.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || path
}

function isLiveState(state: DebugState) {
  return state === 'starting' || state === 'running' || state === 'paused'
}

function emptyTab(partial: Partial<DebugSessionTab> & { id: string; title: string }): DebugSessionTab {
  return {
    program: null,
    module: null,
    state: 'idle',
    error: null,
    frames: [],
    activeFrameId: null,
    scopes: [],
    variablesByRef: {},
    output: [],
    consoleLines: [],
    currentPath: null,
    currentLine: null,
    stopReason: null,
    busy: false,
    lastStartOpts: null,
    ...partial,
  }
}

export const useDebugStore = defineStore('debug', () => {
  const sessions = ref<DebugSessionTab[]>([])
  const activeSessionId = ref<string | null>(null)
  const configs = ref<DebugLaunchConfig[]>([])
  const exceptionFilters = ref<string[]>(['uncaught'])
  /** workspace-relative path → breakpoints (shared, persisted per workspace) */
  const breakpoints = ref<Record<string, DebugBreakpoint[]>>({})
  const watches = ref<WatchItem[]>([])

  const sockets = new Map<string, WebSocket>()
  let bpFileTimer: ReturnType<typeof setTimeout> | null = null
  let bpHydrateGen = 0
  let lastHydratedWorkspaceId: string | null = null

  function breakpointPathKey(path: string) {
    const root = useAppStore().workspace?.root_path
    return normalizeDebugPath(path, root) || path.replace(/\\/g, '/')
  }

  function persistBreakpointsNow(map = breakpoints.value) {
    const app = useAppStore()
    const cleaned = pruneBreakpointsMap(map, app.workspace?.root_path)
    writeBreakpointsLocal(app.workspaceId, cleaned)
  }

  function scheduleWorkspaceFilePersist() {
    const app = useAppStore()
    if (!app.workspaceId) return
    if (bpFileTimer) clearTimeout(bpFileTimer)
    bpFileTimer = setTimeout(() => {
      bpFileTimer = null
      const ws = app.workspaceId
      if (!ws) return
      const body = serializeBreakpointsFile(breakpoints.value)
      void api(`/api/workspaces/${ws}/file?path=${encodeURIComponent(BREAKPOINTS_FILE_REL)}`, {
        method: 'PUT',
        body: JSON.stringify({ content: body }),
      }).catch(() => {
        /* ignore write failures (readonly / missing dir) */
      })
    }, 400)
  }

  function commitBreakpoints(next: Record<string, DebugBreakpoint[]>) {
    const app = useAppStore()
    const cleaned = pruneBreakpointsMap(next, app.workspace?.root_path)
    breakpoints.value = cleaned
    persistBreakpointsNow(cleaned)
    scheduleWorkspaceFilePersist()
    window.dispatchEvent(new CustomEvent('ca-debug-breakpoints-changed'))
  }

  async function hydrateBreakpoints(force = false) {
    const app = useAppStore()
    const ws = app.workspaceId
    if (!ws) {
      breakpoints.value = {}
      lastHydratedWorkspaceId = null
      return
    }
    if (!force && lastHydratedWorkspaceId === ws && Object.keys(breakpoints.value).length) {
      return
    }
    const gen = ++bpHydrateGen
    const local = readBreakpointsLocal(ws)
    breakpoints.value = local
    lastHydratedWorkspaceId = ws
    window.dispatchEvent(new CustomEvent('ca-debug-breakpoints-changed'))

    try {
      const data = await api<{ content: string }>(
        `/api/workspaces/${ws}/file?path=${encodeURIComponent(BREAKPOINTS_FILE_REL)}`,
      )
      if (gen !== bpHydrateGen || useAppStore().workspaceId !== ws) return
      const fromFile = parseBreakpointsFile(data.content || '')
      if (!Object.keys(fromFile).length) {
        if (Object.keys(local).length) scheduleWorkspaceFilePersist()
        return
      }
      if (!Object.keys(local).length) {
        breakpoints.value = fromFile
        writeBreakpointsLocal(ws, fromFile)
        window.dispatchEvent(new CustomEvent('ca-debug-breakpoints-changed'))
        return
      }
      const union: Record<string, DebugBreakpoint[]> = { ...fromFile }
      for (const [path, list] of Object.entries(local)) {
        union[path] = [...(union[path] || []), ...list]
      }
      const finalMap = pruneBreakpointsMap(union, app.workspace?.root_path)
      breakpoints.value = finalMap
      writeBreakpointsLocal(ws, finalMap)
      if (JSON.stringify(finalMap) !== JSON.stringify(fromFile)) scheduleWorkspaceFilePersist()
      window.dispatchEvent(new CustomEvent('ca-debug-breakpoints-changed'))
    } catch {
      if (Object.keys(local).length) scheduleWorkspaceFilePersist()
    }
  }

  // Initial hydrate + reload when workspace changes
  void hydrateBreakpoints(true)
  watch(
    () => useAppStore().workspaceId,
    () => {
      void hydrateBreakpoints(true)
    },
  )

  const activeSession = computed(
    () => sessions.value.find((s) => s.id === activeSessionId.value) || null,
  )

  const sessionId = computed(() => activeSession.value?.id ?? null)
  const state = computed(() => activeSession.value?.state ?? 'idle')
  const error = computed(() => activeSession.value?.error ?? null)
  const frames = computed(() => activeSession.value?.frames ?? [])
  const activeFrameId = computed(() => activeSession.value?.activeFrameId ?? null)
  const scopes = computed(() => activeSession.value?.scopes ?? [])
  const variablesByRef = computed(() => activeSession.value?.variablesByRef ?? {})
  const output = computed(() => activeSession.value?.output ?? [])
  const consoleLines = computed(() => activeSession.value?.consoleLines ?? [])
  const currentPath = computed(() => activeSession.value?.currentPath ?? null)
  const currentLine = computed(() => activeSession.value?.currentLine ?? null)
  const stopReason = computed(() => activeSession.value?.stopReason ?? null)
  const busy = computed(() => activeSession.value?.busy ?? false)

  const paused = computed(() => state.value === 'paused')
  const active = computed(() => sessions.value.some((s) => isLiveState(s.state)))
  const canStart = computed(() => Boolean(useAppStore().workspaceId))
  const canStep = computed(
    () => paused.value && !busy.value && Boolean(sessionId.value),
  )
  const canPause = computed(
    () =>
      Boolean(activeSession.value) &&
      isLiveState(activeSession.value!.state) &&
      !paused.value &&
      !busy.value,
  )
  const canRestart = computed(
    () => Boolean(activeSession.value?.lastStartOpts) && !busy.value,
  )

  function getSession(id: string | null | undefined) {
    if (!id) return null
    return sessions.value.find((s) => s.id === id) || null
  }

  function patchSession(id: string, patch: Partial<DebugSessionTab>) {
    const idx = sessions.value.findIndex((s) => s.id === id)
    if (idx < 0) return
    const next = { ...sessions.value[idx], ...patch }
    sessions.value = [
      ...sessions.value.slice(0, idx),
      next,
      ...sessions.value.slice(idx + 1),
    ]
  }

  async function selectSession(id: string) {
    const sess = getSession(id)
    if (!sess) return
    activeSessionId.value = id
    if (sess.state === 'paused' && sess.currentPath) {
      const line = sess.currentLine && sess.currentLine > 0 ? sess.currentLine : 1
      window.dispatchEvent(
        new CustomEvent('ca-debug-paused', {
          detail: { path: sess.currentPath, line, sessionId: id },
        }),
      )
      await useAppStore().openPathAtLine(sess.currentPath, line)
    } else if (sess.program) {
      await useAppStore().openPathAtLine(sess.program, 1)
    }
  }

  function sessionForProgram(program: string | null | undefined) {
    if (!program) return null
    const norm = program.replace(/\\/g, '/')
    return (
      sessions.value.find(
        (s) => isLiveState(s.state) && (s.program || '').replace(/\\/g, '/') === norm,
      ) || null
    )
  }

  function pausedLineForPath(path: string | null): number | null {
    if (!path) return null
    const root = useAppStore().workspace?.root_path
    for (const s of sessions.value) {
      if (s.state !== 'paused' || !s.currentPath || s.currentLine == null) continue
      const a = normalizeDebugPath(s.currentPath, root) || s.currentPath
      const b = normalizeDebugPath(path, root) || path
      if (a.replace(/\\/g, '/').toLowerCase() === b.replace(/\\/g, '/').toLowerCase()) {
        return s.currentLine
      }
    }
    return null
  }

  function breakpointsFor(path: string): DebugBreakpoint[] {
    const key = breakpointPathKey(path)
    return breakpoints.value[key] || breakpoints.value[path] || []
  }

  function toggleBreakpoint(path: string, line: number) {
    const key = breakpointPathKey(path)
    const list = [...breakpointsFor(path)]
    const idx = list.findIndex((b) => b.line === line)
    if (idx >= 0) list.splice(idx, 1)
    else list.push({ line })
    commitBreakpoints({ ...breakpoints.value, [key]: list })
    void syncBreakpoints(key)
  }

  function setBreakpointCondition(path: string, line: number, condition: string) {
    const key = breakpointPathKey(path)
    const list = [...breakpointsFor(path)]
    const bp = list.find((b) => b.line === line)
    if (!bp) return
    bp.condition = condition.trim() || undefined
    commitBreakpoints({ ...breakpoints.value, [key]: list })
    void syncBreakpoints(key)
  }

  async function syncBreakpoints(path: string) {
    const payload = breakpointsFor(path)
    await Promise.all(
      sessions.value
        .filter((s) => isLiveState(s.state) && !s.id.startsWith('pending-'))
        .map(async (s) => {
          try {
            await api(`/api/debug/sessions/${s.id}/breakpoints`, {
              method: 'POST',
              body: JSON.stringify({ path, breakpoints: payload }),
            })
          } catch {
            /* ignore */
          }
        }),
    )
  }

  async function loadConfigs() {
    const app = useAppStore()
    if (!app.workspaceId) {
      configs.value = []
      return
    }
    try {
      const data = await api<{ configurations: DebugLaunchConfig[] }>(
        `/api/debug/configs?workspace_id=${encodeURIComponent(app.workspaceId)}`,
      )
      configs.value = data.configurations || []
    } catch {
      configs.value = []
    }
  }

  function disconnectWs(id: string) {
    const socket = sockets.get(id)
    if (!socket) return
    try {
      socket.close()
    } catch {
      /* ignore */
    }
    sockets.delete(id)
  }

  function removeSessionLocal(id: string) {
    disconnectWs(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (activeSessionId.value === id) {
      activeSessionId.value = sessions.value[0]?.id ?? null
    }
  }

  function connectWs(id: string) {
    disconnectWs(id)
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const socket = new WebSocket(`${proto}://${location.host}/api/debug/sessions/${id}/ws`)
    sockets.set(id, socket)
    socket.onopen = () => {
      void syncSessionState(id)
    }
    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data || '{}')) as {
          type?: string
          payload?: Record<string, unknown>
        }
        void handleEvent(id, msg.type || '', msg.payload || {})
      } catch {
        /* ignore */
      }
    }
    socket.onclose = () => {
      if (sockets.get(id) === socket) sockets.delete(id)
      const sess = getSession(id)
      // Boot may have failed before the client subscribed; surface the error instead of spinning.
      if (sess && (sess.state === 'starting' || sess.busy)) {
        patchSession(id, {
          state: 'error',
          busy: false,
          error: sess.error || t('debug.startFailed'),
        })
      }
    }
  }

  async function applyStoppedPayload(id: string, payload: Record<string, unknown>) {
    const app = useAppStore()
    const root = app.workspace?.root_path
    let nextFrames = Array.isArray(payload.frames) ? (payload.frames as DebugFrame[]) : []
    nextFrames = nextFrames.map((fr) => ({
      ...fr,
      path: fr.path ? normalizeDebugPath(fr.path, root) || fr.path : fr.path,
    }))
    if ((!nextFrames.length || !nextFrames[0]?.path) && id) {
      try {
        const data = await api<{ stackFrames: DebugFrame[] }>(
          `/api/debug/sessions/${id}/stackTrace`,
        )
        nextFrames = (data.stackFrames || []).map((fr) => ({
          ...fr,
          path: fr.path ? normalizeDebugPath(fr.path, root) || fr.path : fr.path,
        }))
      } catch {
        /* keep empty */
      }
    }
    let top = nextFrames[0]
    if (!top && payload.currentPath) {
      top = {
        id: 0,
        name: '',
        path: normalizeDebugPath(String(payload.currentPath), root) || String(payload.currentPath),
        line: typeof payload.currentLine === 'number' ? payload.currentLine : 1,
      }
      nextFrames = [top]
    }
    const rawLine = typeof top?.line === 'number' ? top.line : null
    const line = rawLine != null && rawLine > 0 ? rawLine : rawLine === 0 ? 1 : null
    const path = top?.path || null
    patchSession(id, {
      state: 'paused',
      frames: nextFrames,
      activeFrameId: top?.id ?? null,
      stopReason: String(payload.reason || payload.description || ''),
      currentPath: path,
      currentLine: line,
    })
    activeSessionId.value = id
    window.dispatchEvent(
      new CustomEvent('ca-debug-paused', {
        detail: { path, line, sessionId: id },
      }),
    )
    if (path) await app.openPathAtLine(path, line || 1)
    if (top?.id != null) await loadScopes(top.id, id)
    await refreshWatches(id)
  }

  async function syncSessionState(id?: string) {
    const sid = id || activeSessionId.value
    if (!sid) return
    try {
      const data = await api<{
        state: DebugState
        frames?: DebugFrame[]
        threadId?: number | null
        currentPath?: string | null
        currentLine?: number | null
      }>(`/api/debug/sessions/${sid}`)
      patchSession(sid, { state: data.state })
      if (data.state === 'paused') {
        await applyStoppedPayload(sid, {
          frames: data.frames || [],
          threadId: data.threadId,
          reason: getSession(sid)?.stopReason || 'breakpoint',
          currentPath: data.currentPath,
          currentLine: data.currentLine,
        })
      }
    } catch {
      /* session may have ended */
    }
  }

  async function handleEvent(id: string, type: string, payload: Record<string, unknown>) {
    const sess = getSession(id)
    if (!sess) return
    if (type === 'session') {
      const next = String(payload.state || '') as DebugState
      if (!next) return
      if (next === 'terminated' || next === 'stopped') {
        disconnectWs(id)
        window.dispatchEvent(new CustomEvent('ca-debug-ended', { detail: { sessionId: id } }))
        removeSessionLocal(id)
        return
      }
      // Do not clobber a live pause with a stale "running" session event.
      if (next === 'running' && sess.state === 'paused') return
      patchSession(id, {
        state: next,
        busy: next === 'starting' ? sess.busy : false,
        ...(next === 'running' ? { currentLine: null, stopReason: null } : {}),
      })
      if (next === 'running') {
        window.dispatchEvent(new CustomEvent('ca-debug-resumed', { detail: { sessionId: id } }))
      }
      return
    }
    if (type === 'error') {
      patchSession(id, {
        error: String(payload.message || t('debug.startFailed')),
        state: 'error',
        busy: false,
      })
      return
    }
    if (type === 'output') {
      const text = String(payload.output || '')
      const trimmed = text.trimEnd()
      if (!trimmed.trim() || /^(ptvsd|debugpy|pydevd)$/i.test(trimmed.trim())) return
      if (/^\s*(?:ptvsd|debugpy|pydevd)(?:\s|$)/i.test(trimmed.trim())) return
      const lineText = trimmed.replace(/\r$/, '')
      // Append each physical line so multi-line chunks stay readable.
      const chunks = lineText.split(/\n/)
      const nextLines = [...sess.consoleLines]
      const nextOut = [...sess.output]
      for (const chunk of chunks) {
        if (!chunk.trim() && chunk === '') continue
        nextOut.push(chunk.endsWith('\n') ? chunk : `${chunk}\n`)
        nextLines.push({ text: chunk, kind: 'stdout' })
      }
      if (nextLines.length === sess.consoleLines.length) return
      patchSession(id, {
        output: nextOut.slice(-400),
        consoleLines: nextLines.slice(-400),
      })
      return
    }
    if (type === 'stopped') {
      patchSession(id, { busy: false })
      await applyStoppedPayload(id, payload)
      return
    }
    if (type === 'exited' || type === 'terminated') {
      disconnectWs(id)
      window.dispatchEvent(new CustomEvent('ca-debug-ended', { detail: { sessionId: id } }))
      removeSessionLocal(id)
      return
    }
  }

  async function start(opts?: StartOpts) {
    const app = useAppStore()
    if (!app.workspaceId) {
      return
    }
    const configName = opts?.configName ?? null
    const program =
      opts?.program ||
      (!configName && app.activePath?.toLowerCase().endsWith('.py') ? app.activePath : null)
    if (!program && !opts?.module && !configName) {
      // surface on a transient tab-less error via existing UI: create ephemeral error on active or toast path
      if (activeSession.value) {
        patchSession(activeSession.value.id, { error: t('debug.needPythonFile') })
      }
      return
    }

    // Same file already debugging → restart that session instead of duplicating
    const existing = program ? sessionForProgram(program) : null
    if (existing) {
      activeSessionId.value = existing.id
      await restart(existing.id)
      return
    }

    const title = basename(program || opts?.module || 'debug')
    const tempId = `pending-${Date.now()}`
    const startOpts: StartOpts = {
      program: opts?.program || program || undefined,
      module: opts?.module,
      configName,
      stopOnEntry: opts?.stopOnEntry ?? false,
    }
    const pending = emptyTab({
      id: tempId,
      title,
      program: program || null,
      module: opts?.module || null,
      state: 'starting',
      busy: true,
      lastStartOpts: startOpts,
    })
    sessions.value = [...sessions.value, pending]
    activeSessionId.value = tempId

    try {
      const bpPayload: Record<string, DebugBreakpoint[]> = {}
      for (const [path, list] of Object.entries(breakpoints.value)) {
        bpPayload[path] = list
      }
      const session = await api<{ id: string; state: string }>('/api/debug/sessions', {
        method: 'POST',
        body: JSON.stringify({
          workspace_id: app.workspaceId,
          program: opts?.module ? null : program,
          module: opts?.module || null,
          currentFile: app.activePath,
          configName: configName || null,
          stopOnEntry: opts?.stopOnEntry ?? false,
          justMyCode: true,
          exceptionFilters: exceptionFilters.value,
          breakpoints: bpPayload,
        }),
      })
      // Replace pending id with real session id; handshake continues in background.
      sessions.value = sessions.value.map((s) =>
        s.id === tempId
          ? {
              ...s,
              id: session.id,
              state: (session.state as DebugState) || 'starting',
              busy: true,
              error: null,
            }
          : s,
      )
      activeSessionId.value = session.id
      connectWs(session.id)
      window.dispatchEvent(new CustomEvent('ca-open-panel', { detail: { id: 'debug' } }))
      void syncSessionState(session.id)
    } catch (err) {
      const code = getErrorCode(err)
      let message = err instanceof Error ? err.message : t('debug.startFailed')
      if (code === 'debug.start_failed' && message.includes('debugpy')) {
        message = t('debug.needDebugpy')
      }
      patchSession(tempId, { state: 'error', busy: false, error: message })
    }
  }

  async function callControl(
    action: 'continue' | 'next' | 'stepIn' | 'stepOut' | 'pause' | 'stop',
    id?: string,
  ) {
    const sid = id || activeSessionId.value
    if (!sid) return
    const sess = getSession(sid)
    if (!sess && action === 'stop') return
    patchSession(sid, { busy: true })
    try {
      if (action === 'stop') {
        try {
          await api(`/api/debug/sessions/${sid}/stop`, { method: 'POST' })
        } catch {
          /* still clear locally */
        }
        removeSessionLocal(sid)
        return
      }
      await api(`/api/debug/sessions/${sid}/${action}`, { method: 'POST' })
      if (action === 'continue' || action === 'next' || action === 'stepIn' || action === 'stepOut') {
        patchSession(sid, {
          state: 'running',
          currentLine: null,
          stopReason: null,
          busy: false,
        })
        window.dispatchEvent(new CustomEvent('ca-debug-resumed', { detail: { sessionId: sid } }))
        return
      }
      patchSession(sid, { busy: false })
    } catch (err) {
      patchSession(sid, {
        busy: false,
        error: err instanceof Error ? err.message : t('debug.controlFailed'),
      })
    }
  }

  async function restart(id?: string) {
    const sid = id || activeSessionId.value
    const sess = getSession(sid)
    if (!sid || !sess?.lastStartOpts) return
    const opts = { ...sess.lastStartOpts }
    await callControl('stop', sid)
    await start(opts)
  }

  async function closeSession(id: string) {
    const sess = getSession(id)
    if (!sess) return
    if (isLiveState(sess.state)) {
      await callControl('stop', id)
    } else {
      removeSessionLocal(id)
    }
  }

  async function loadScopes(frameId: number, id?: string) {
    const sid = id || activeSessionId.value
    if (!sid) return
    const sess = getSession(sid)
    if (!sess) return
    const frame = sess.frames.find((f) => f.id === frameId)
    const path = frame?.path
      ? normalizeDebugPath(frame.path, useAppStore().workspace?.root_path)
      : null
    const line = typeof frame?.line === 'number' ? frame.line : null
    patchSession(sid, {
      activeFrameId: frameId,
      currentPath: path,
      currentLine: line,
    })
    if (frame) {
      window.dispatchEvent(
        new CustomEvent('ca-debug-paused', {
          detail: { path, line, sessionId: sid },
        }),
      )
    }
    try {
      const data = await api<{ scopes: DebugScope[] }>(
        `/api/debug/sessions/${sid}/scopes?frameId=${frameId}`,
      )
      const nextScopes = data.scopes || []
      patchSession(sid, { scopes: nextScopes, variablesByRef: {} })
      for (const scope of nextScopes) {
        await loadVariables(scope.variablesReference, sid)
      }
    } catch {
      patchSession(sid, { scopes: [] })
    }
  }

  async function loadVariables(ref: number, id?: string) {
    const sid = id || activeSessionId.value
    if (!sid || !ref) return
    const sess = getSession(sid)
    if (!sess) return
    try {
      const data = await api<{ variables: Record<string, unknown>[] }>(
        `/api/debug/sessions/${sid}/variables?variablesReference=${ref}`,
      )
      const list: DebugVariable[] = (data.variables || []).map((raw) => ({
        name: String(raw.name ?? ''),
        value: raw.value != null ? String(raw.value) : undefined,
        type: raw.type != null ? String(raw.type) : undefined,
        variablesReference: Number(raw.variablesReference || 0) || undefined,
        namedVariables:
          typeof raw.namedVariables === 'number' ? raw.namedVariables : undefined,
        indexedVariables:
          typeof raw.indexedVariables === 'number' ? raw.indexedVariables : undefined,
        presentationHint:
          raw.presentationHint && typeof raw.presentationHint === 'object'
            ? (raw.presentationHint as DebugVariable['presentationHint'])
            : undefined,
      }))
      patchSession(sid, {
        variablesByRef: { ...getSession(sid)!.variablesByRef, [ref]: list },
      })
    } catch {
      patchSession(sid, {
        variablesByRef: { ...getSession(sid)!.variablesByRef, [ref]: [] },
      })
    }
  }

  async function evaluate(expression: string, context = 'repl', id?: string) {
    const sid = id || activeSessionId.value
    const sess = getSession(sid)
    if (!sid || !sess || !expression.trim()) return
    patchSession(sid, {
      consoleLines: [...sess.consoleLines, { text: expression, kind: 'in' }],
    })
    try {
      const data = await api<{ result?: string }>(`/api/debug/sessions/${sid}/evaluate`, {
        method: 'POST',
        body: JSON.stringify({
          expression,
          frameId: sess.activeFrameId,
          context,
        }),
      })
      const cur = getSession(sid)
      if (!cur) return
      patchSession(sid, {
        consoleLines: [...cur.consoleLines, { text: String(data.result ?? ''), kind: 'out' }],
      })
    } catch (err) {
      const cur = getSession(sid)
      if (!cur) return
      patchSession(sid, {
        consoleLines: [
          ...cur.consoleLines,
          { text: err instanceof Error ? err.message : String(err), kind: 'err' },
        ],
      })
    }
  }

  async function setVariable(
    variablesReference: number,
    name: string,
    value: string,
    id?: string,
  ): Promise<{ ok: true; value?: string } | { ok: false; error: string }> {
    const sid = id || activeSessionId.value
    const sess = getSession(sid)
    if (!sid || !sess || sess.state !== 'paused' || !variablesReference || !name) {
      return { ok: false, error: t('debug.setValueNeedPause') }
    }
    try {
      const data = await api<{
        value?: string
        type?: string
        variablesReference?: number
        namedVariables?: number
        indexedVariables?: number
      }>(`/api/debug/sessions/${sid}/setVariable`, {
        method: 'POST',
        body: JSON.stringify({ variablesReference, name, value }),
      })
      const cur = getSession(sid)
      if (!cur) return { ok: true, value: data.value != null ? String(data.value) : undefined }
      const list = [...(cur.variablesByRef[variablesReference] || [])]
      const idx = list.findIndex((v) => v.name === name)
      if (idx >= 0) {
        const prev = list[idx]
        list[idx] = {
          ...prev,
          value: data.value != null ? String(data.value) : prev.value,
          type: data.type != null ? String(data.type) : prev.type,
          variablesReference: Number(data.variablesReference || 0) || undefined,
          namedVariables:
            typeof data.namedVariables === 'number' ? data.namedVariables : prev.namedVariables,
          indexedVariables:
            typeof data.indexedVariables === 'number' ? data.indexedVariables : prev.indexedVariables,
        }
        patchSession(sid, {
          variablesByRef: { ...cur.variablesByRef, [variablesReference]: list },
        })
      } else {
        await loadVariables(variablesReference, sid)
      }
      void refreshWatches(sid)
      return { ok: true, value: data.value != null ? String(data.value) : undefined }
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) }
    }
  }

  function addWatch(expression: string) {
    const expr = expression.trim()
    if (!expr) return
    watches.value = [...watches.value, { id: `w${bpIdSeq++}`, expression: expr }]
    void refreshWatches()
  }

  function removeWatch(id: string) {
    watches.value = watches.value.filter((w) => w.id !== id)
  }

  async function refreshWatches(id?: string) {
    const sid = id || activeSessionId.value
    const sess = getSession(sid)
    if (!sess || sess.state !== 'paused') return
    const next: WatchItem[] = []
    for (const item of watches.value) {
      try {
        const data = await api<{ result?: string }>(`/api/debug/sessions/${sid}/evaluate`, {
          method: 'POST',
          body: JSON.stringify({
            expression: item.expression,
            frameId: sess.activeFrameId,
            context: 'watch',
          }),
        })
        next.push({ ...item, value: String(data.result ?? ''), error: undefined })
      } catch (err) {
        next.push({
          ...item,
          value: undefined,
          error: err instanceof Error ? err.message : String(err),
        })
      }
    }
    watches.value = next
  }

  async function setExceptionFilters(filters: string[]) {
    exceptionFilters.value = filters
    const sid = activeSessionId.value
    if (!sid) return
    try {
      await api(`/api/debug/sessions/${sid}/exceptionBreakpoints`, {
        method: 'POST',
        body: JSON.stringify({ filters }),
      })
    } catch {
      /* ignore */
    }
  }

  function reset() {
    for (const s of [...sessions.value]) {
      disconnectWs(s.id)
    }
    sessions.value = []
    activeSessionId.value = null
  }

  return {
    sessions,
    activeSessionId,
    activeSession,
    sessionId,
    state,
    error,
    frames,
    activeFrameId,
    scopes,
    variablesByRef,
    output,
    configs,
    exceptionFilters,
    breakpoints,
    watches,
    consoleLines,
    currentPath,
    currentLine,
    stopReason,
    busy,
    paused,
    active,
    canStart,
    canStep,
    canPause,
    canRestart,
    breakpointsFor,
    toggleBreakpoint,
    setBreakpointCondition,
    hydrateBreakpoints,
    loadConfigs,
    start,
    restart,
    closeSession,
    selectSession,
    sessionForProgram,
    pausedLineForPath,
    syncSessionState,
    callControl,
    loadScopes,
    loadVariables,
    evaluate,
    setVariable,
    addWatch,
    removeWatch,
    refreshWatches,
    setExceptionFilters,
    reset,
  }
})
