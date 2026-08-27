import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { api, subscribeRun, type StreamEnvelope } from '@/api/http'
import { applyEvent, type ChatMessage } from '@/protocol/applyEvent'
import type { ThinkingLevel } from '@/types/thinking'
import { loadThinkingLevel } from '@/types/thinking'
import { classifyOpenKind, isEditableKind, isPreviewKind, rawFileUrl, type OpenFileKind } from '@/preview/classify'
import { t } from '@/i18n'

export type Workspace = {
  id: string
  name: string
  root_path: string
  last_opened_at?: string | null
}
export type Conversation = {
  id: string
  title: string
  mode: string
  model_id: string | null
  active_run_id: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type FsItem = { name: string; path: string; is_dir: boolean }
export type OpenFile = {
  path: string
  kind: OpenFileKind
  content: string
  previewUrl?: string
  mime?: string
  dirty: boolean
  readonly?: boolean
}
export type FileReview = {
  path: string
  action: string
  before: string
  after: string
  status: 'pending' | 'accepted' | 'rejected'
  blockId: string
}

export type QueuedSend = {
  id: string
  conversationId: string
  text: string
  references: { type: string; path: string }[]
  files: { name: string; url: string; size: number; type: string }[]
  mode: 'ask' | 'agent' | 'plan'
  modelId: string | null
  thinkingLevel: ThinkingLevel
  skillName?: string | null
}

const SEND_QUEUE_KEY = 'ca.send_queue'

function loadSendQueue(): QueuedSend[] {
  try {
    const raw = localStorage.getItem(SEND_QUEUE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is QueuedSend => {
      if (!item || typeof item !== 'object') return false
      const row = item as Partial<QueuedSend>
      return typeof row.id === 'string' && typeof row.conversationId === 'string' && typeof row.text === 'string'
    })
  } catch {
    return []
  }
}

function persistSendQueue(queue: QueuedSend[]) {
  try {
    localStorage.setItem(SEND_QUEUE_KEY, JSON.stringify(queue))
  } catch {
    /* ignore quota */
  }
}

export const useAppStore = defineStore('app', () => {
  const workspaces = ref<Workspace[]>([])
  const workspaceId = ref<string | null>(localStorage.getItem('ca.workspace'))
  const conversations = ref<Conversation[]>([])
  const conversationId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const runStatus = ref<string>('idle')
  const lastEventId = ref<string | null>(null)
  const applied = ref<Set<string>>(new Set())
  const mode = ref<'ask' | 'agent' | 'plan'>('agent')
  const modelId = ref<string | null>(null)
  const thinkingLevel = ref<ThinkingLevel>(loadThinkingLevel())
  watch(thinkingLevel, (level) => {
    localStorage.setItem('ca.thinking_level', level)
    localStorage.setItem('ca.thinking', level === 'off' ? '0' : '1')
  })
  const thinking = computed(() => thinkingLevel.value !== 'off')
  const sampling = ref<{ temperature: number | null }>({ temperature: null })
  const fileTree = ref<FsItem[]>([])
  const childrenMap = ref<Record<string, FsItem[]>>({})
  const expanded = ref<Set<string>>(new Set())
  const treePath = ref('')
  const openFiles = ref<OpenFile[]>([])
  const activePath = ref<string | null>(null)
  const openFile = computed(() => openFiles.value.find((f) => f.path === activePath.value) || null)
  const editorCopyContext = ref<{
    path: string
    text: string
    startLine: number
    endLine: number
  } | null>(null)
  const fileNotice = ref<string | null>(null)
  const pendingReveal = ref<{
    path: string
    line: number
    query?: string
    caseSensitive?: boolean
  } | null>(null)
  const searchIntent = ref<{
    seq: number
    include?: string | null
    addExclude?: string
    clearInclude?: boolean
  }>({ seq: 0 })

  function openSearch(opts?: { include?: string | null; addExclude?: string; clearInclude?: boolean }) {
    searchIntent.value = { seq: searchIntent.value.seq + 1, ...opts }
    window.dispatchEvent(new CustomEvent('ca-open-search'))
  }

  function openExplorerPanel() {
    activity.value = 'explorer'
    window.dispatchEvent(new CustomEvent('ca-open-explorer'))
  }

  const skillFocusIntent = ref<{ seq: number; name?: string }>({ seq: 0 })

  function openSkill(name?: string) {
    const skillName = name?.trim()
    activity.value = 'skills'
    window.dispatchEvent(new CustomEvent('ca-open-skills'))
    queueMicrotask(() => {
      skillFocusIntent.value = {
        seq: skillFocusIntent.value.seq + 1,
        ...(skillName ? { name: skillName } : {}),
      }
    })
  }

  const reviews = ref<Record<string, FileReview>>({})
  const confirmDialog = ref<{
    title: string
    summary: string
    details?: string
    confirmLabel?: string
    cancelLabel?: string
    danger?: boolean
  } | null>(null)
  const activeRunId = ref<string | null>(null)
  const sendQueue = ref<QueuedSend[]>(loadSendQueue())
  watch(
    sendQueue,
    (queue) => {
      persistSendQueue(queue)
    },
    { deep: true },
  )
  let queueFlushing = false
  let suppressQueueFlush = false
  let stopStream: (() => void) | null = null
  let confirmResolver: ((ok: boolean) => void) | null = null
  /** Coalesce block.delta to one Vue update per animation frame. */
  let pendingDeltas: StreamEnvelope[] = []
  let deltaRaf = 0
  /** Hold non-thinking blocks until the active thinking card finishes. */
  let heldEvents: StreamEnvelope[] = []
  const providers = ref<any[]>([])
  const skills = ref<any[]>([])
  const conversationSkills = ref<Record<string, string>>({})
  const settings = ref<{ schema: any; values: Record<string, unknown> } | null>(null)
  const activity = ref('agent')
  const pendingModelProbe = ref(false)
  const gitChangedPaths = ref<Record<string, string>>({})
  const sessionTreeMarks = ref<Record<string, string>>({})
  const ackedTreeMarks = ref<Record<string, true>>({})
  let treeTimer: ReturnType<typeof setTimeout> | null = null
  const pendingTreePaths = new Set<string>()

  const workspace = computed(() => workspaces.value.find((w) => w.id === workspaceId.value) || null)

  const recentWorkspaces = computed(() =>
    [...workspaces.value].sort((a, b) => {
      const ta = a.last_opened_at ? Date.parse(a.last_opened_at) : 0
      const tb = b.last_opened_at ? Date.parse(b.last_opened_at) : 0
      return tb - ta
    }),
  )

  async function loadWorkspaces() {
    workspaces.value = await api('/api/workspaces')
    if (workspaceId.value && !workspaces.value.some((w) => w.id === workspaceId.value)) {
      workspaceId.value = workspaces.value[0]?.id ?? null
    }
  }

  async function addWorkspace(root_path: string, name?: string) {
    const ws = await api<Workspace>('/api/workspaces', {
      method: 'POST',
      body: JSON.stringify({ root_path, name }),
    })
    await loadWorkspaces()
    await selectWorkspace(ws.id)
  }

  function clearWorkspace() {
    detachRun()
    workspaceId.value = null
    localStorage.removeItem('ca.workspace')
    conversationId.value = null
    messages.value = []
    conversations.value = []
    openFiles.value = []
    activePath.value = null
    reviews.value = {}
    confirmDialog.value = null
    fileTree.value = []
    childrenMap.value = {}
    expanded.value = new Set()
    treePath.value = ''
    gitChangedPaths.value = {}
    sessionTreeMarks.value = {}
    ackedTreeMarks.value = {}
  }

  function conversationStorageKey(wsId: string) {
    return `ca.conversation.${wsId}`
  }

  function expandedStorageKey(wsId: string) {
    return `ca.tree.expanded.${wsId}`
  }

  function readExpanded(wsId: string) {
    try {
      const raw = localStorage.getItem(expandedStorageKey(wsId))
      const parsed = raw ? JSON.parse(raw) : []
      return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string' && item.length > 0) : []
    } catch {
      return []
    }
  }

  function persistExpanded() {
    const ws = workspaceId.value
    if (!ws) return
    localStorage.setItem(expandedStorageKey(ws), JSON.stringify([...expanded.value].slice(0, 500)))
  }

  function setExpanded(next: Set<string>) {
    expanded.value = next
    persistExpanded()
  }

  function rememberConversation(id: string | null) {
    const ws = workspaceId.value
    if (!ws) return
    const key = conversationStorageKey(ws)
    if (id) localStorage.setItem(key, id)
    else localStorage.removeItem(key)
  }

  async function selectWorkspace(id: string) {
    await api(`/api/workspaces/${id}/open`, { method: 'POST' })
    workspaceId.value = id
    localStorage.setItem('ca.workspace', id)
    const savedExpanded = readExpanded(id)
    treePath.value = ''
    childrenMap.value = {}
    expanded.value = new Set()
    gitChangedPaths.value = {}
    sessionTreeMarks.value = {}
    ackedTreeMarks.value = {}
    await Promise.all([loadConversations(), loadTree(''), loadSkills(), loadProviders(), loadGitChangedPaths()])
    await restoreExpandedDirs(savedExpanded)
    const saved = localStorage.getItem(conversationStorageKey(id))
    const restore =
      (saved && conversations.value.some((c) => c.id === saved) && saved) ||
      conversations.value[0]?.id ||
      null
    if (restore) {
      await openConversation(restore)
    } else {
      await newChat()
    }
    openExplorerPanel()
    await loadWorkspaces()
  }

  async function loadTree(path = '') {
    if (!workspaceId.value) return
    const ws = workspaceId.value
    const data = await api<{ items: typeof fileTree.value }>(
      `/api/workspaces/${workspaceId.value}/tree?path=${encodeURIComponent(path)}`,
    )
    if (workspaceId.value !== ws) return
    const next = childrenMap.value
    next[path] = data.items
    childrenMap.value = { ...next }
    if (!path) fileTree.value = data.items
    treePath.value = path
  }

  function isExpanded(path: string) {
    return expanded.value.has(path)
  }

  function depthOf(path: string) {
    return path.split('/').filter(Boolean).length
  }

  async function restoreExpandedDirs(paths: string[]) {
    const sorted = [...new Set(paths)].sort((a, b) => depthOf(a) - depthOf(b) || a.localeCompare(b))
    const kept = new Set<string>()
    for (const path of sorted) {
      const parent = parentPath(path)
      if (parent && !kept.has(parent)) continue
      try {
        await loadTree(path)
      } catch {
        continue
      }
      if (childrenOf(parent).some((item) => item.is_dir && item.path === path)) kept.add(path)
    }
    setExpanded(kept)
  }

  async function toggleDir(path: string) {
    const next = new Set(expanded.value)
    if (next.has(path)) {
      next.delete(path)
      setExpanded(next)
      return
    }
    next.add(path)
    setExpanded(next)
    await loadTree(path)
  }

  async function expandDir(path: string) {
    if (!path) return
    if (!expanded.value.has(path)) {
      setExpanded(new Set([...expanded.value, path]))
    }
    await loadTree(path)
  }

  async function refreshTree() {
    const open = [...expanded.value].sort((a, b) => depthOf(a) - depthOf(b) || a.localeCompare(b))
    await Promise.all([loadTree(''), loadGitChangedPaths()])
    const kept = new Set<string>()
    for (const path of open) {
      const parent = parentPath(path)
      if (parent && !kept.has(parent)) continue
      try {
        await loadTree(path)
      } catch {
        continue
      }
      if (childrenOf(parent).some((item) => item.is_dir && item.path === path)) kept.add(path)
    }
    setExpanded(kept)
  }

  function collapseAllDirs() {
    setExpanded(new Set())
  }

  const EXPAND_SKIP_DIRS = new Set([
    'node_modules',
    'bower_components',
    'vendor',
    'venv',
    '.venv',
    'dist',
    'build',
    'out',
    'target',
    '__pycache__',
    '.git',
    '.next',
    '.nuxt',
    '.output',
    '.turbo',
    '.cache',
    'coverage',
    'Pods',
  ])

  function shouldSkipExpand(item: FsItem) {
    if (EXPAND_SKIP_DIRS.has(item.name)) return true
    return item.path.split('/').some((part) => EXPAND_SKIP_DIRS.has(part))
  }

  async function expandAllDirs() {
    const next = new Set<string>()
    let layer = ['']
    while (layer.length) {
      await Promise.all(layer.map((dir) => loadTree(dir)))
      const childDirs: string[] = []
      for (const dir of layer) {
        for (const item of childrenOf(dir)) {
          if (!item.is_dir || shouldSkipExpand(item)) continue
          next.add(item.path)
          childDirs.push(item.path)
        }
      }
      layer = childDirs
    }
    setExpanded(next)
  }

  function gitMarkKey(code: string) {
    if (code.includes('?')) return 'untracked'
    if (code.includes('A')) return 'added'
    if (code.includes('D')) return 'deleted'
    if (code.includes('M')) return 'modified'
    return 'changed'
  }

  function treeTitle(key: string) {
    const i18nKey = `tree.${key}`
    return t(i18nKey)
  }

  async function loadGitChangedPaths() {
    if (!workspaceId.value) {
      gitChangedPaths.value = {}
      return
    }
    try {
      const status = await api<{ ok: boolean; files: { path: string; code: string }[] }>(
        `/api/workspaces/${workspaceId.value}/git/status`,
      )
      if (!status.ok) {
        gitChangedPaths.value = {}
        return
      }
      const next: Record<string, string> = {}
      for (const file of status.files) {
        next[file.path] = gitMarkKey(file.code)
      }
      const prev = gitChangedPaths.value
      const same =
        Object.keys(next).length === Object.keys(prev).length &&
        Object.keys(next).every((path) => prev[path] === next[path])
      if (!same) gitChangedPaths.value = next
      if (Object.keys(next).length) {
        const session = { ...sessionTreeMarks.value }
        for (const path of Object.keys(next)) delete session[path]
        sessionTreeMarks.value = session
      }
    } catch {
      gitChangedPaths.value = {}
    }
  }

  async function revealInTree(relPath: string) {
    if (!relPath) return
    const parts = relPath.split('/').filter(Boolean)
    const next = new Set(expanded.value)
    let acc = ''
    for (let i = 0; i < parts.length - 1; i++) {
      acc = acc ? `${acc}/${parts[i]}` : parts[i]
      next.add(acc)
      await loadTree(acc)
    }
    expanded.value = next
    persistExpanded()
    await loadTree(parentPath(relPath) || '')
  }

  function scheduleTreeRefresh(relPath?: string) {
    if (relPath) pendingTreePaths.add(relPath)
    // Trailing debounce: wait until writes settle (tool.call often fires before the file exists)
    if (treeTimer) clearTimeout(treeTimer)
    treeTimer = setTimeout(async () => {
      treeTimer = null
      const paths = [...pendingTreePaths]
      pendingTreePaths.clear()
      try {
        if (!paths.length) {
          await refreshTree()
          return
        }
        for (const path of paths) {
          await revealInTree(path)
          const parent = parentPath(path)
          if (parent) await loadTree(parent)
        }
        await loadTree('')
        await loadGitChangedPaths()
      } catch (err) {
        console.error(err)
      }
    }, 350)
  }

  function childrenOf(path: string) {
    return childrenMap.value[path] || []
  }

  function parentPath(path: string) {
    const i = path.lastIndexOf('/')
    return i <= 0 ? '' : path.slice(0, i)
  }

  function joinPath(dir: string, name: string) {
    return dir ? `${dir.replace(/\/$/, '')}/${name}` : name
  }

  async function createEntry(relPath: string, kind: 'file' | 'dir') {
    if (!workspaceId.value) return
    await api(`/api/workspaces/${workspaceId.value}/entries`, {
      method: 'POST',
      body: JSON.stringify({ path: relPath, kind }),
    })
    await loadTree(parentPath(relPath) || '')
    if (kind === 'dir') {
      setExpanded(new Set([...expanded.value, parentPath(relPath) || '', relPath].filter(Boolean)))
      await loadTree(relPath)
    } else if (parentPath(relPath)) {
      setExpanded(new Set([...expanded.value, parentPath(relPath)]))
    }
    if (kind === 'file') {
      sessionTreeMarks.value = { ...sessionTreeMarks.value, [relPath]: 'added' }
      await openPath(relPath, false)
    }
    void loadGitChangedPaths()
  }

  async function renameEntry(from: string, to: string) {
    if (!workspaceId.value) return
    await api(`/api/workspaces/${workspaceId.value}/rename`, {
      method: 'POST',
      body: JSON.stringify({ path: from, new_path: to }),
    })
    if (openFiles.value.some((f) => f.path === from)) {
      openFiles.value = openFiles.value.map((f) => {
        if (f.path !== from) return f
        const next: typeof f = { ...f, path: to }
        if (isPreviewKind(f.kind) && workspaceId.value) {
          next.previewUrl = rawFileUrl(workspaceId.value, to)
        }
        return next
      })
      if (activePath.value === from) activePath.value = to
    }
    const session = { ...sessionTreeMarks.value }
    if (session[from]) {
      session[to] = session[from]
      delete session[from]
      sessionTreeMarks.value = session
    }
    await loadTree(parentPath(to) || '')
    void loadGitChangedPaths()
  }

  async function deleteEntry(relPath: string) {
    if (!workspaceId.value) return
    await api(`/api/workspaces/${workspaceId.value}/entries?path=${encodeURIComponent(relPath)}`, {
      method: 'DELETE',
    })
    openFiles.value = openFiles.value.filter((f) => f.path !== relPath && !f.path.startsWith(`${relPath}/`))
    if (activePath.value === relPath || activePath.value?.startsWith(`${relPath}/`)) {
      activePath.value = openFiles.value.at(-1)?.path ?? null
    }
    const parent = parentPath(relPath)
    if (expanded.value.has(relPath)) {
      const next = new Set(expanded.value)
      next.delete(relPath)
      setExpanded(next)
    }
    await loadTree(parent)
    const session = { ...sessionTreeMarks.value }
    delete session[relPath]
    for (const key of Object.keys(session)) {
      if (key.startsWith(`${relPath}/`)) delete session[key]
    }
    sessionTreeMarks.value = session
    void loadGitChangedPaths()
  }

  async function openPath(path: string, isDir: boolean) {
    if (isDir) {
      await toggleDir(path)
      return
    }
    const existing = openFiles.value.find((f) => f.path === path)
    const review = reviews.value[path]
    const kind = classifyOpenKind(path)

    if (existing) {
      if (!existing.dirty && workspaceId.value) {
        if (existing.kind === 'html') {
          existing.previewUrl = rawFileUrl(workspaceId.value, path)
          try {
            const data = await api<{ path: string; content: string }>(
              `/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(path)}`,
            )
            existing.content = data.content
            window.dispatchEvent(new CustomEvent('ca-file-reload', { detail: { path, content: data.content } }))
          } catch {
            /* keep previous content */
          }
        } else if (isPreviewKind(existing.kind)) {
          existing.previewUrl = rawFileUrl(workspaceId.value, path)
        } else {
          try {
            const data = await api<{ path: string; content: string }>(
              `/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(path)}`,
            )
            existing.content = data.content
            window.dispatchEvent(new CustomEvent('ca-file-reload', { detail: { path, content: data.content } }))
          } catch {
            if (review) {
              existing.content = review.after
              window.dispatchEvent(new CustomEvent('ca-file-reload', { detail: { path, content: review.after } }))
            }
          }
        }
      }
      activePath.value = path
      window.dispatchEvent(new Event('ca-focus-editor'))
      return
    }

    if (!workspaceId.value) return
    const ws = workspaceId.value

    if (kind === 'html') {
      try {
        const data = await api<{ path: string; content: string }>(
          `/api/workspaces/${ws}/file?path=${encodeURIComponent(path)}`,
        )
        openFiles.value = [
          ...openFiles.value,
          {
            path: data.path,
            kind: 'html',
            content: data.content,
            previewUrl: rawFileUrl(ws, data.path),
            dirty: false,
          },
        ]
        activePath.value = data.path
        window.dispatchEvent(new Event('ca-focus-editor'))
        return
      } catch (err) {
        fileNotice.value = err instanceof Error ? err.message : String(err)
        return
      }
    }

    if (isPreviewKind(kind)) {
      const url = rawFileUrl(ws, path)
      openFiles.value = [
        ...openFiles.value,
        { path, kind, content: '', previewUrl: url, dirty: false },
      ]
      activePath.value = path
      window.dispatchEvent(new Event('ca-focus-editor'))
      return
    }

    try {
      const data = await api<{ path: string; content: string }>(
        `/api/workspaces/${ws}/file?path=${encodeURIComponent(path)}`,
      )
      openFiles.value = [...openFiles.value, { path: data.path, kind: 'text', content: data.content, dirty: false }]
      activePath.value = data.path
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      // Unknown/binary: fall back to binary preview tab
      if (msg.includes('file.binary') || msg.includes('Binary file')) {
        try {
          const url = rawFileUrl(ws, path)
          openFiles.value = [
            ...openFiles.value,
            { path, kind: 'binary', content: '', previewUrl: url, dirty: false },
          ]
          activePath.value = path
        } catch (fallbackErr) {
          fileNotice.value = fallbackErr instanceof Error ? fallbackErr.message : String(fallbackErr)
          return
        }
      } else if (review) {
        openFiles.value = [...openFiles.value, { path, kind: 'text', content: review.after, dirty: false }]
        activePath.value = path
      } else {
        fileNotice.value = msg || t('file.openFailed')
        return
      }
    }
    window.dispatchEvent(new Event('ca-focus-editor'))
  }

  function clearFileNotice() {
    fileNotice.value = null
  }

  function setEditorCopyContext(ctx: { path: string; text: string; startLine: number; endLine: number }) {
    editorCopyContext.value = ctx
  }

  function clearEditorCopyContext() {
    editorCopyContext.value = null
  }

  async function openAgentFile(path: string) {
    if (!path) return
    activity.value = 'explorer'
    await revealInTree(path)
    await openPath(path, false)
  }

  async function openRevisionFile(relPath: string, rev = 'HEAD') {
    if (!workspaceId.value || !relPath) return
    const tabPath = `${rev}:${relPath}`
    const kind = classifyOpenKind(relPath)
    try {
      const data = await api<{ path: string; content: string }>(
        `/api/workspaces/${workspaceId.value}/git/blob?path=${encodeURIComponent(relPath)}&rev=${encodeURIComponent(rev)}`,
      )
      const existing = openFiles.value.find((f) => f.path === tabPath)
      if (existing) {
        existing.content = data.content
        existing.dirty = false
        existing.readonly = true
        activePath.value = tabPath
      } else {
        openFiles.value = [
          ...openFiles.value,
          {
            path: tabPath,
            kind: isPreviewKind(kind) ? 'text' : kind,
            content: data.content,
            dirty: false,
            readonly: true,
          },
        ]
        activePath.value = tabPath
      }
      window.dispatchEvent(new CustomEvent('ca-file-reload', { detail: { path: tabPath, content: data.content } }))
      window.dispatchEvent(new Event('ca-focus-editor'))
    } catch (err) {
      fileNotice.value = err instanceof Error ? err.message : String(err)
    }
  }

  async function openPathAtLine(
    path: string,
    line: number,
    opts?: { query?: string; caseSensitive?: boolean },
  ) {
    pendingReveal.value = {
      path,
      line: Math.max(1, line),
      query: opts?.query?.trim() || undefined,
      caseSensitive: Boolean(opts?.caseSensitive),
    }
    await openPath(path, false)
  }

  function pendingReview(path: string | null | undefined) {
    if (!path) return null
    const review = reviews.value[path]
    return review?.status === 'pending' ? review : null
  }

  const pendingReviews = computed(() => Object.values(reviews.value).filter((r) => r.status === 'pending'))

  async function acceptAllReviews() {
    const paths = pendingReviews.value.map((r) => r.path)
    for (const path of paths) await acceptReview(path)
  }

  async function cycleReview(delta: number) {
    const list = pendingReviews.value.map((r) => r.path)
    if (!list.length) return
    const i = list.indexOf(activePath.value || '')
    const start = i < 0 ? (delta > 0 ? -1 : 0) : i
    const next = list[(start + delta + list.length) % list.length]
    await openAgentFile(next)
  }

  function upsertReview(block: { id: string; type: string; meta: Record<string, unknown> }) {
    if (block.type !== 'file.diff' && block.type !== 'file.delete') return
    const path = String(block.meta.path || '')
    if (!path) return
    const before = typeof block.meta.before === 'string' ? block.meta.before : null
    const after = typeof block.meta.after === 'string' ? block.meta.after : null
    if (before === null && after === null) return
    reviews.value = {
      ...reviews.value,
      [path]: {
        path,
        action: String(block.meta.action || (block.type === 'file.delete' ? 'delete' : 'edit')),
        before: before ?? '',
        after: after ?? '',
        status: 'pending',
        blockId: block.id,
      },
    }
    const isNew = !before && after
    if (isNew) {
      sessionTreeMarks.value = { ...sessionTreeMarks.value, [path]: 'addedPending' }
    }
    if (ackedTreeMarks.value[path]) {
      const acked = { ...ackedTreeMarks.value }
      delete acked[path]
      ackedTreeMarks.value = acked
    }
  }

  async function syncOpenFile(path: string, content: string, dirty = false) {
    const file = openFiles.value.find((f) => f.path === path)
    if (file) {
      file.content = content
      file.dirty = dirty
      window.dispatchEvent(new CustomEvent('ca-file-reload', { detail: { path, content } }))
    }
  }

  async function acceptReview(path: string) {
    const review = reviews.value[path]
    if (!review || review.status !== 'pending') return
    reviews.value = { ...reviews.value, [path]: { ...review, status: 'accepted' } }
    await syncOpenFile(path, review.after, false)
    const session = { ...sessionTreeMarks.value }
    delete session[path]
    sessionTreeMarks.value = session
    ackedTreeMarks.value = { ...ackedTreeMarks.value, [path]: true }
    void loadGitChangedPaths()
  }

  async function rejectReview(path: string) {
    const review = reviews.value[path]
    if (!review || review.status !== 'pending' || !workspaceId.value) return
    const created = review.action === 'create' || !review.before
    if (review.action === 'delete') {
      await api(`/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(path)}`, {
        method: 'PUT',
        body: JSON.stringify({ content: review.before }),
      })
      await syncOpenFile(path, review.before, false)
      await revealInTree(path)
    } else if (created) {
      try {
        await api(`/api/workspaces/${workspaceId.value}/entries?path=${encodeURIComponent(path)}`, {
          method: 'DELETE',
        })
      } catch {
        /* already gone */
      }
      closeFile(path)
      await loadTree(parentPath(path) || '')
    } else {
      await api(`/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(path)}`, {
        method: 'PUT',
        body: JSON.stringify({ content: review.before }),
      })
      await syncOpenFile(path, review.before, false)
    }
    reviews.value = { ...reviews.value, [path]: { ...review, status: 'rejected' } }
    void loadGitChangedPaths()
  }

  function activateFile(path: string) {
    if (openFiles.value.some((f) => f.path === path)) activePath.value = path
  }

  function closeFile(path: string) {
    const i = openFiles.value.findIndex((f) => f.path === path)
    if (i < 0) return
    const next = openFiles.value.filter((f) => f.path !== path)
    openFiles.value = next
    if (activePath.value === path) {
      const neighbor = next[i] || next[i - 1]
      activePath.value = neighbor?.path ?? null
    }
  }

  function closeOtherFiles(path: string) {
    const keep = openFiles.value.find((f) => f.path === path)
    if (!keep) return
    openFiles.value = [keep]
    activePath.value = path
  }

  function closeFilesToTheRight(path: string) {
    const i = openFiles.value.findIndex((f) => f.path === path)
    if (i < 0) return
    openFiles.value = openFiles.value.slice(0, i + 1)
    if (!openFiles.value.some((f) => f.path === activePath.value)) activePath.value = path
  }

  function closeAllFiles() {
    openFiles.value = []
    activePath.value = null
  }

  function updateOpenContent(path: string, content: string) {
    const file = openFiles.value.find((f) => f.path === path)
    if (!file || file.readonly || !isEditableKind(file.kind) || file.content === content) return
    file.content = content
    file.dirty = true
    if (ackedTreeMarks.value[path]) {
      const acked = { ...ackedTreeMarks.value }
      delete acked[path]
      ackedTreeMarks.value = acked
    }
  }

  async function saveOpenFile() {
    const file = openFile.value
    if (!workspaceId.value || !file || file.readonly || !isEditableKind(file.kind)) return
    await api(`/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(file.path)}`, {
      method: 'PUT',
      body: JSON.stringify({ content: file.content }),
    })
    file.dirty = false
    if (file.kind === 'html') {
      file.previewUrl = rawFileUrl(workspaceId.value, file.path)
    }
    void loadGitChangedPaths()
  }

  async function reloadOpenFile(path: string) {
    if (!workspaceId.value) return
    const file = openFiles.value.find((f) => f.path === path)
    if (!file || !isEditableKind(file.kind)) return
    try {
      const head = path.match(/^(HEAD|[0-9a-fA-F]{7,40}):(.+)$/)
      const data = head
        ? await api<{ path: string; content: string }>(
            `/api/workspaces/${workspaceId.value}/git/blob?path=${encodeURIComponent(head[2])}&rev=${encodeURIComponent(head[1])}`,
          )
        : await api<{ path: string; content: string }>(
            `/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(path)}`,
          )
      file.content = data.content
      file.dirty = false
      window.dispatchEvent(new CustomEvent('ca-file-reload', { detail: { path, content: data.content } }))
    } catch {
      /* keep previous */
    }
  }

  async function loadConversations() {
    if (!workspaceId.value) return
    conversations.value = await api(`/api/workspaces/${workspaceId.value}/conversations`)
  }

  async function newChat() {
    if (!workspaceId.value) return
    const conv = await api<Conversation>('/api/conversations', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: workspaceId.value, mode: mode.value, model_id: modelId.value }),
    })
    await loadConversations()
    await openConversation(conv.id)
  }

  function discardPendingDeltas() {
    if (deltaRaf) {
      cancelAnimationFrame(deltaRaf)
      deltaRaf = 0
    }
    pendingDeltas = []
    heldEvents = []
  }

  function hasStreamingThinking(runId?: string | null): boolean {
    const rid = runId || activeRunId.value
    if (!rid) return false
    for (const m of messages.value) {
      if (m.run_id !== rid && m.id !== `run-${rid}`) continue
      if (m.blocks.some((b) => b.type === 'assistant.thinking' && b.status === 'streaming')) return true
    }
    return false
  }

  function heldBlockIds(): Set<string> {
    const ids = new Set<string>()
    for (const ev of heldEvents) {
      if (ev.type === 'block.started' && ev.payload?.block_id) ids.add(String(ev.payload.block_id))
    }
    return ids
  }

  function releaseHeldEvents() {
    if (!heldEvents.length) return
    const batch = heldEvents
    heldEvents = []
    for (const ev of batch) applyIncomingEvent(ev)
  }

  function applyIncomingEvent(event: StreamEnvelope) {
    messages.value = applyEvent(messages.value, event)
    const payload = event.payload || {}
    const blockId = payload.block_id != null ? String(payload.block_id) : ''
    let type = String(payload.block_type || '')
    let meta = (payload.meta as Record<string, unknown>) || {}
    let path = eventPath(event)

    // completed events often omit block_type/meta — recover from the applied block
    if ((!type || !path) && blockId) {
      for (const m of messages.value) {
        const b = m.blocks.find((item) => item.id === blockId)
        if (!b) continue
        if (!type) type = b.type
        if (!path && typeof b.meta.path === 'string') path = b.meta.path
        if (!Object.keys(meta).length) meta = b.meta || {}
        break
      }
    }

    if (
      (event.type === 'block.started' || event.type === 'block.completed') &&
      (type === 'file.diff' || type === 'file.delete')
    ) {
      upsertReview({
        id: blockId,
        type,
        meta,
      })
      const changedPath = String(meta.path || path || '')
      if (changedPath && typeof meta.after === 'string') {
        const file = openFiles.value.find((f) => f.path === changedPath)
        if (file && !file.dirty) {
          file.content = meta.after
          window.dispatchEvent(new CustomEvent('ca-file-reload', { detail: { path: changedPath, content: meta.after } }))
        }
      }
      if (type === 'file.diff' && (meta.action === 'create' || meta.action === 'overwrite') && changedPath) {
        if (meta.action === 'create') {
          sessionTreeMarks.value = { ...sessionTreeMarks.value, [changedPath]: 'added' }
        }
      }
    }
    if (event.type === 'run.started') runStatus.value = 'running'
    if (event.type === 'run.completed' || event.type === 'run.failed' || event.type === 'run.cancelled') {
      runStatus.value = event.type.replace('run.', '')
      const now = new Date().toISOString()
      messages.value = messages.value.map((m) =>
        m.run_id === event.run_id ? { ...m, ended_at: now } : m,
      )
      void refreshTree()
      if (activeRunId.value === event.run_id) activeRunId.value = null
      void flushSendQueue()
    }
    if (event.type === 'block.started' || event.type === 'block.completed') {
      const name = String((meta as { name?: string }).name || '')
      const fileOp =
        type.startsWith('file.') ||
        ['write_file', 'search_replace', 'delete_file', 'read_file'].includes(name)
      if (fileOp) scheduleTreeRefresh(path || undefined)
    }
  }

  function detachRun() {
    discardPendingDeltas()
    stopStream?.()
    stopStream = null
    activeRunId.value = null
    runStatus.value = 'idle'
    lastEventId.value = null
  }

  async function openConversation(id: string) {
    // Leave the previous run stream behind so the new chat is not "busy"
    detachRun()
    conversationId.value = id
    rememberConversation(id)
    messages.value = []
    const data = await api<Conversation & { messages: ChatMessage[]; active_run: any }>(`/api/conversations/${id}`)
    // Ignore late responses if user already switched again
    if (conversationId.value !== id) return
    messages.value = data.messages || []
    mode.value = (data.mode as typeof mode.value) || 'agent'
    modelId.value = data.model_id
    applied.value = new Set()
    const active = data.active_run
    if (active && ['queued', 'running'].includes(String(active.status))) {
      lastEventId.value = active.last_event_id
      attachRun(active.id, active.last_event_id)
    } else {
      runStatus.value = 'idle'
      activeRunId.value = null
      lastEventId.value = null
    }
  }

  async function deleteConversation(id: string) {
    const target = conversations.value.find((c) => c.id === id)
    const ok = await askConfirm({
      title: t('confirm.deleteSessionTitle'),
      summary: target ? t('confirm.deleteSessionNamed', { title: target.title }) : t('confirm.deleteSession'),
      confirmLabel: t('common.delete'),
      cancelLabel: t('common.cancel'),
      danger: true,
    })
    if (!ok) return

    await api(`/api/conversations/${id}`, { method: 'DELETE' })
    conversations.value = conversations.value.filter((c) => c.id !== id)

    if (conversationId.value !== id) return

    detachRun()
    messages.value = []
    conversationId.value = null

    if (conversations.value[0]) {
      await openConversation(conversations.value[0].id)
      return
    }
    await newChat()
  }

  function eventPath(event: StreamEnvelope): string | null {
    const payload = event.payload || {}
    const meta = (payload.meta || {}) as Record<string, unknown>
    if (typeof meta.path === 'string' && meta.path) return meta.path
    let args: unknown = meta.args
    if (typeof args === 'string') {
      try {
        args = JSON.parse(args)
      } catch {
        args = null
      }
    }
    if (args && typeof args === 'object' && typeof (args as { path?: unknown }).path === 'string') {
      return (args as { path: string }).path
    }
    return null
  }

  function flushPendingDeltas() {
    if (deltaRaf) {
      cancelAnimationFrame(deltaRaf)
      deltaRaf = 0
    }
    if (!pendingDeltas.length) return
    const batch = pendingDeltas
    pendingDeltas = []
    let next = messages.value
    for (const event of batch) {
      next = applyEvent(next, event)
    }
    messages.value = next
  }

  function scheduleDeltaFlush() {
    if (deltaRaf) return
    deltaRaf = requestAnimationFrame(() => {
      deltaRaf = 0
      flushPendingDeltas()
    })
  }

  function onEvent(event: StreamEnvelope) {
    // Drop events from a run we already navigated away from
    if (!activeRunId.value || event.run_id !== activeRunId.value) return
    if (applied.value.has(event.event_id)) return
    applied.value.add(event.event_id)
    lastEventId.value = event.event_id

    const payload = event.payload || {}
    const blockId = payload.block_id != null ? String(payload.block_id) : ''
    const blockType = String(payload.block_type || '')

    // While thinking is still streaming, hold tool/file/markdown cards (and their follow-ups)
    if (event.type === 'block.started' && blockType !== 'assistant.thinking' && hasStreamingThinking(event.run_id)) {
      heldEvents.push(event)
      return
    }
    if (
      (event.type === 'block.delta' || event.type === 'block.completed') &&
      blockId &&
      heldBlockIds().has(blockId)
    ) {
      heldEvents.push(event)
      return
    }

    // One paint per frame while streaming text/thinking
    if (event.type === 'block.delta') {
      pendingDeltas.push(event)
      scheduleDeltaFlush()
      return
    }

    flushPendingDeltas()
    const completedThink =
      event.type === 'block.completed' &&
      (blockType === 'assistant.thinking' ||
        messages.value.some((m) =>
          m.blocks.some((b) => b.id === blockId && b.type === 'assistant.thinking'),
        ))
    applyIncomingEvent(event)

    if (completedThink && !hasStreamingThinking(event.run_id)) {
      releaseHeldEvents()
    }
    if (event.type === 'run.completed' || event.type === 'run.failed' || event.type === 'run.cancelled') {
      releaseHeldEvents()
    }
  }

  function attachRun(runId: string, after?: string | null) {
    discardPendingDeltas()
    stopStream?.()
    stopStream = null
    activeRunId.value = runId
    runStatus.value = 'running'
    stopStream = subscribeRun(runId, after || null, onEvent, () => {
      // Stream closed after we already switched conversations — ignore
      if (activeRunId.value !== runId) return
      discardPendingDeltas()
      runStatus.value = runStatus.value === 'running' ? 'completed' : runStatus.value
      activeRunId.value = null
      loadConversations()
      void flushSendQueue()
    })
  }

  function isRunBusy() {
    return runStatus.value === 'running' || runStatus.value === 'queued' || Boolean(activeRunId.value)
  }

  function conversationQueue() {
    const cid = conversationId.value
    if (!cid) return []
    return sendQueue.value.filter((item) => item.conversationId === cid)
  }

  function conversationSkillName(cid?: string | null) {
    const id = cid ?? conversationId.value
    if (!id) return null
    return conversationSkills.value[id] ?? null
  }

  function setConversationSkill(name: string | null, cid?: string | null) {
    const id = cid ?? conversationId.value
    if (!id) return
    const next = { ...conversationSkills.value }
    if (name) next[id] = name
    else delete next[id]
    conversationSkills.value = next
  }

  function enqueueSend(
    text: string,
    references: { type: string; path: string }[] = [],
    files: { name: string; url: string; size: number; type: string }[] = [],
  ) {
    if (!conversationId.value) return
    sendQueue.value = [
      ...sendQueue.value,
      {
        id: `q-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        conversationId: conversationId.value,
        text,
        references,
        files,
        mode: mode.value,
        modelId: modelId.value,
        thinkingLevel: thinkingLevel.value,
        skillName: conversationSkillName(),
      },
    ]
  }

  function removeQueuedSend(id: string) {
    sendQueue.value = sendQueue.value.filter((item) => item.id !== id)
  }

  function clearConversationQueue(cid?: string | null) {
    const id = cid ?? conversationId.value
    if (!id) return
    sendQueue.value = sendQueue.value.filter((item) => item.conversationId !== id)
  }

  async function waitUntilIdle(timeoutMs = 20000) {
    const start = Date.now()
    while (isRunBusy() && Date.now() - start < timeoutMs) {
      await new Promise((resolve) => setTimeout(resolve, 120))
    }
  }

  async function dispatchSend(
    text: string,
    references: { type: string; path: string }[] = [],
    files: { name: string; url: string; size: number; type: string }[] = [],
    opts?: {
      mode?: 'ask' | 'agent' | 'plan'
      modelId?: string | null
      thinkingLevel?: ThinkingLevel
      skillName?: string | null
    },
  ) {
    if (!conversationId.value) await newChat()
    if (!conversationId.value) return
    const sendMode = opts?.mode ?? mode.value
    const sendModel = opts?.modelId ?? modelId.value
    const sendThinking = opts?.thinkingLevel ?? thinkingLevel.value
    const sendSkill = opts?.skillName !== undefined ? opts.skillName : conversationSkillName()
    messages.value = [
      ...messages.value,
      {
        id: `local-${Date.now()}`,
        role: 'user',
        created_at: new Date().toISOString(),
        blocks: [
          {
            id: 'u',
            type: 'user.text',
            text,
            meta: {
              ...(files.length ? { files } : {}),
              ...(sendSkill ? { skill: { name: sendSkill } } : {}),
            },
            status: 'ok',
          },
        ],
      },
    ]
    const data = await api<{ run_id: string }>(`/api/conversations/${conversationId.value}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        text,
        mode: sendMode,
        model_id: sendModel,
        thinking_level: sendThinking,
        thinking: sendThinking !== 'off',
        references,
        files,
        skill_name: sendSkill || undefined,
      }),
    })
    lastEventId.value = null
    attachRun(data.run_id, null)
  }

  async function flushSendQueue() {
    if (suppressQueueFlush || queueFlushing || isRunBusy()) return
    const cid = conversationId.value
    if (!cid) return
    const next = sendQueue.value.find((item) => item.conversationId === cid)
    if (!next) return
    queueFlushing = true
    sendQueue.value = sendQueue.value.filter((item) => item.id !== next.id)
    try {
      await dispatchSend(next.text, next.references, next.files, {
        mode: next.mode,
        modelId: next.modelId,
        thinkingLevel: next.thinkingLevel,
        skillName: next.skillName ?? null,
      })
    } catch (err) {
      sendQueue.value = [next, ...sendQueue.value]
      console.error(err)
    } finally {
      queueFlushing = false
    }
  }

  async function send(
    text: string,
    references: { type: string; path: string }[] = [],
    files: { name: string; url: string; size: number; type: string }[] = [],
  ) {
    if (!conversationId.value) await newChat()
    if (!conversationId.value) return
    if (isRunBusy()) {
      enqueueSend(text, references, files)
      return
    }
    await dispatchSend(text, references, files)
  }

  async function sendNow(
    text: string,
    references: { type: string; path: string }[] = [],
    files: { name: string; url: string; size: number; type: string }[] = [],
  ) {
    if (!conversationId.value) await newChat()
    if (!conversationId.value) return
    suppressQueueFlush = true
    try {
      if (isRunBusy()) {
        await stop()
        await waitUntilIdle()
      }
      await dispatchSend(text, references, files)
    } finally {
      suppressQueueFlush = false
    }
  }

  async function sendQueuedNow(id: string) {
    const item = sendQueue.value.find((q) => q.id === id)
    if (!item) return
    sendQueue.value = sendQueue.value.filter((q) => q.id !== id)
    suppressQueueFlush = true
    try {
      if (isRunBusy()) {
        await stop()
        await waitUntilIdle()
      }
      await dispatchSend(item.text, item.references, item.files, {
        mode: item.mode,
        modelId: item.modelId,
        thinkingLevel: item.thinkingLevel,
        skillName: item.skillName ?? null,
      })
    } catch (err) {
      sendQueue.value = [item, ...sendQueue.value]
      console.error(err)
    } finally {
      suppressQueueFlush = false
    }
  }

  async function stop() {
    const conv = conversations.value.find((c) => c.id === conversationId.value)
    const runId = activeRunId.value || conv?.active_run_id
    if (!runId) return
    await api(`/api/runs/${runId}/cancel`, { method: 'POST' })
  }

  function askConfirm(req: {
    title: string
    summary: string
    details?: string
    confirmLabel?: string
    cancelLabel?: string
    danger?: boolean
  }): Promise<boolean> {
    confirmResolver?.(false)
    confirmDialog.value = { danger: true, confirmLabel: t('common.confirm'), cancelLabel: t('common.cancel'), ...req }
    return new Promise((resolve) => {
      confirmResolver = resolve
    })
  }

  function closeConfirm(ok: boolean) {
    confirmDialog.value = null
    const resolver = confirmResolver
    confirmResolver = null
    resolver?.(ok)
  }

  function decideApproval(approvalId: string, allowed: boolean) {
    const runId = activeRunId.value
    if (!runId) return
    api(`/api/runs/${runId}/approvals/${approvalId}`, {
      method: 'POST',
      body: JSON.stringify({ allowed }),
    }).catch(() => undefined)
  }

  async function loadProviders() {
    providers.value = await api('/api/llm/providers')
    const models = providers.value.flatMap((p) => p.models || [])
    if (!models.length) {
      modelId.value = ''
      return
    }
    const available = models.filter((m: any) => m.availability?.ok === true)
    const pool = available.length ? available : models
    const current = models.find((m: any) => m.id === modelId.value)
    const currentOk = current && (available.length ? current.availability?.ok === true : true)
    if (!currentOk) {
      const def = pool.find((m: any) => m.is_default) || pool[0]
      if (def) modelId.value = def.id
    } else if (!modelId.value) {
      const def = pool.find((m: any) => m.is_default) || pool[0]
      if (def) modelId.value = def.id
    }
  }

  async function loadSkills() {
    const q = workspaceId.value ? `?workspace_id=${workspaceId.value}` : ''
    skills.value = await api(`/api/skills${q}`)
  }

  async function loadSettings() {
    settings.value = await api('/api/settings')
  }

  async function saveSettings(patch: Record<string, unknown>) {
    settings.value = await api('/api/settings', { method: 'PATCH', body: JSON.stringify(patch) })
  }

  function isFileDirty(path: string) {
    return openFiles.value.some((f) => f.path === path && f.dirty)
  }

  const markedAncestorPaths = computed(() => {
    const out = new Set<string>()
    const addAncestors = (path: string) => {
      const parts = path.split('/').filter(Boolean)
      let acc = ''
      for (let i = 0; i < parts.length - 1; i++) {
        acc = acc ? `${acc}/${parts[i]}` : parts[i]
        out.add(acc)
      }
    }
    for (const file of openFiles.value) {
      if (file.dirty) addAncestors(file.path)
    }
    for (const [path, review] of Object.entries(reviews.value)) {
      if (review.status === 'pending') addAncestors(path)
    }
    for (const path of Object.keys(gitChangedPaths.value)) {
      if (!ackedTreeMarks.value[path]) addAncestors(path)
    }
    for (const path of Object.keys(sessionTreeMarks.value)) {
      if (!ackedTreeMarks.value[path]) addAncestors(path)
    }
    return out
  })

  function fileTreeMark(path: string, isDir = false) {
    if (isDir) {
      const own = gitChangedPaths.value[path] || sessionTreeMarks.value[path]
      if (own) return { show: true, title: treeTitle(own) }
      if (markedAncestorPaths.value.has(path)) return { show: true, title: t('tree.containsChanges') }
      return { show: false, title: '' }
    }
    if (isFileDirty(path)) return { show: true, title: t('tree.unsaved') }
    const review = pendingReview(path)
    if (review) {
      const isNew = review.action === 'create' || !review.before
      return { show: true, title: isNew ? t('tree.addedPending') : t('tree.modifiedPending') }
    }
    if (ackedTreeMarks.value[path]) return { show: false, title: '' }
    const gitTitle = gitChangedPaths.value[path]
    if (gitTitle) return { show: true, title: treeTitle(gitTitle) }
    const sessionTitle = sessionTreeMarks.value[path]
    if (sessionTitle) return { show: true, title: treeTitle(sessionTitle) }
    return { show: false, title: '' }
  }

  return {
    workspaces,
    recentWorkspaces,
    workspaceId,
    workspace,
    conversations,
    conversationId,
    messages,
    runStatus,
    sendQueue,
    mode,
    modelId,
    thinkingLevel,
    thinking,
    sampling,
    fileTree,
    childrenMap,
    expanded,
    treePath,
    openFiles,
    activePath,
    openFile,
    editorCopyContext,
    setEditorCopyContext,
    clearEditorCopyContext,
    fileNotice,
    clearFileNotice,
    pendingReveal,
    searchIntent,
    openSearch,
    openExplorerPanel,
    skillFocusIntent,
    openSkill,
    reviews,
    pendingReview,
    pendingReviews,
    acceptAllReviews,
    cycleReview,
    confirmDialog,
    askConfirm,
    closeConfirm,
    decideApproval,
    providers,
    skills,
    conversationSkills,
    settings,
    activity,
    pendingModelProbe,
    loadWorkspaces,
    addWorkspace,
    clearWorkspace,
    selectWorkspace,
    loadTree,
    refreshTree,
    collapseAllDirs,
    expandAllDirs,
    revealInTree,
    toggleDir,
    expandDir,
    isExpanded,
    childrenOf,
    parentPath,
    joinPath,
    createEntry,
    renameEntry,
    deleteEntry,
    openPath,
    openPathAtLine,
    openAgentFile,
    openRevisionFile,
    acceptReview,
    rejectReview,
    activateFile,
    closeFile,
    closeOtherFiles,
    closeFilesToTheRight,
    closeAllFiles,
    updateOpenContent,
    saveOpenFile,
    reloadOpenFile,
    isFileDirty,
    fileTreeMark,
    loadGitChangedPaths,
    gitChangedPaths,
    loadConversations,
    newChat,
    openConversation,
    deleteConversation,
    send,
    sendNow,
    sendQueuedNow,
    stop,
    removeQueuedSend,
    clearConversationQueue,
    conversationQueue,
    isRunBusy,
    loadProviders,
    loadSkills,
    conversationSkillName,
    setConversationSkill,
    loadSettings,
    saveSettings,
  }
})
