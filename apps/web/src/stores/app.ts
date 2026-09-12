import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { api, subscribeRun, type StreamConnectionState, type StreamEnvelope } from '@/api/http'
import { useToast } from '@/composables/useToast'
import { applyEvent, type ChatMessage } from '@/protocol/applyEvent'
import type { ThinkingLevel } from '@/types/thinking'
import { loadThinkingLevel } from '@/types/thinking'
import { classifyOpenKind, isEditableKind, isPreviewKind, rawFileUrl, type OpenFileKind } from '@/preview/classify'
import { gitMarkKind, gitMarkLetter, gitMarkTitle, type GitMarkKind, type GitPathMark } from '@/utils/gitStatus'
import { draftCommitFromPaths } from '@/utils/gitCommitDraft'
import { notifyApprovalRequired, playTaskCompleteSound } from '@/utils/notificationSound'
import { pendingApprovalsFromMessages, settleUndecidedApprovals } from '@/utils/approvals'
import { parseChatFileRef } from '@/utils/chatFileLinks'
import { acceptHunkIntoBefore, rejectHunkFromAfter, textsEqual } from '@/utils/diffHunk'
import { t } from '@/i18n'
import { fileRelativePath } from '@/utils/fsDrop'

export type Workspace = {
  id: string
  name: string
  root_path: string
  kind?: 'local' | 'ssh'
  ssh_host?: string | null
  ssh_port?: number | null
  ssh_user?: string | null
  ssh_display_name?: string | null
  has_ssh_secret?: boolean
  display_path?: string | null
  created_at?: string | null
  last_opened_at?: string | null
  /** Present after status/open probes — directory missing on disk/remote. */
  root_missing?: boolean
  root_ok?: boolean
}
export type Conversation = {
  id: string
  title: string
  mode: string
  model_id: string | null
  active_run_id: string | null
  run_status?: string | null
  awaiting_approval?: boolean
  archived?: boolean
  turn_count?: number
  snippet?: string | null
  match?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type FsItem = {
  name: string
  path: string
  is_dir: boolean
  size?: number | null
  mtime?: number | null
  ignored?: boolean
}
export type FileTreeMark = {
  show: boolean
  title: string
  kind: GitMarkKind | ''
  letter?: string
}
export type OpenFile = {
  path: string
  kind: OpenFileKind
  content: string
  previewUrl?: string
  mime?: string
  dirty: boolean
  readonly?: boolean
}
export type GitEditorDiff = {
  original: string
  modifiedReadonly?: boolean
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
  references: {
    type: string
    path: string
    text?: string
    line_start?: number
    line_end?: number
    title?: string
  }[]
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
  /** Current workspace root missing on disk / remote (from status poll). */
  const workspaceRootMissing = ref(false)
  let workspaceStatusTimer: ReturnType<typeof setInterval> | null = null
  let workspaceStatusInFlight = false
  const WORKSPACE_STATUS_MS = 10_000
  /** Non-null while switching conversation / workspace — shown as loading tip in Agent panel. */
  const switchLoading = ref<string | null>(null)
  let switchLoadGen = 0
  const runStatus = ref<string>('idle')
  /** SSE projection for the active run: idle | live | reconnecting | disconnected */
  const streamConnection = ref<'idle' | 'live' | 'reconnecting' | 'disconnected'>('idle')
  let streamResumeAfter: string | null = null
  const toast = useToast()
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
  const suppressEditorPersist = ref(false)
  const activePath = ref<string | null>(null)
  const openFile = computed(() => openFiles.value.find((f) => f.path === activePath.value) || null)
  const editorCopyContext = ref<{
    path: string
    text: string
    startLine: number
    endLine: number
  } | null>(null)
  const terminalCopyContext = ref<{
    text: string
    startLine: number
    endLine: number
    title: string
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

  const reviews = ref<Record<string, FileReview[]>>({})
  const activeReviewIndex = ref<Record<string, number>>({})
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
  const gitChangedPaths = ref<Record<string, GitPathMark>>({})
  const gitRepoOk = ref(false)
  const gitCommitDraft = ref('')
  const gitEditorDiff = ref<Record<string, GitEditorDiff>>({})
  const sessionTreeMarks = ref<Record<string, string>>({})
  const ackedTreeMarks = ref<Record<string, true>>({})
  let treeTimer: ReturnType<typeof setTimeout> | null = null
  const pendingTreePaths = new Set<string>()

  const workspace = computed(() => workspaces.value.find((w) => w.id === workspaceId.value) || null)

  const recentWorkspaces = computed(() =>
    [...workspaces.value].sort((a, b) => {
      const ta = a.created_at ? Date.parse(a.created_at) : 0
      const tb = b.created_at ? Date.parse(b.created_at) : 0
      return tb - ta
    }),
  )

  function stopWorkspaceStatusWatch() {
    if (workspaceStatusTimer) {
      clearInterval(workspaceStatusTimer)
      workspaceStatusTimer = null
    }
  }

  function patchWorkspaceStatus(id: string, missing: boolean) {
    workspaces.value = workspaces.value.map((w) =>
      w.id === id ? { ...w, root_missing: missing, root_ok: !missing } : w,
    )
  }

  async function refreshWorkspaceStatus() {
    const id = workspaceId.value
    if (!id) {
      workspaceRootMissing.value = false
      return
    }
    if (workspaceStatusInFlight) return
    workspaceStatusInFlight = true
    try {
      const st = await api<Workspace & { root_missing?: boolean; root_ok?: boolean }>(
        `/api/workspaces/${id}/status`,
      )
      if (workspaceId.value !== id) return
      const missing = Boolean(st.root_missing ?? st.root_ok === false)
      workspaceRootMissing.value = missing
      patchWorkspaceStatus(id, missing)
    } catch {
      /* transient network — keep last known state */
    } finally {
      workspaceStatusInFlight = false
    }
  }

  function startWorkspaceStatusWatch() {
    stopWorkspaceStatusWatch()
    void refreshWorkspaceStatus()
    workspaceStatusTimer = setInterval(() => {
      void refreshWorkspaceStatus()
    }, WORKSPACE_STATUS_MS)
  }

  async function loadWorkspaces() {
    workspaces.value = await api('/api/workspaces')
    if (workspaceId.value && !workspaces.value.some((w) => w.id === workspaceId.value)) {
      workspaceId.value = workspaces.value[0]?.id ?? null
    }
  }

  async function addWorkspace(root_path: string, name?: string) {
    const ws = await api<Workspace>('/api/workspaces', {
      method: 'POST',
      body: JSON.stringify({ root_path, name, kind: 'local' }),
    })
    await loadWorkspaces()
    await selectWorkspace(ws.id)
  }

  async function addSshWorkspace(payload: {
    root_path: string
    name?: string
    ssh_display_name?: string
    ssh_host: string
    ssh_port?: number
    ssh_user: string
    ssh_password?: string
    ssh_private_key?: string
    ssh_passphrase?: string
    reuse_ssh_from?: string
  }) {
    const ws = await api<Workspace>('/api/workspaces', {
      method: 'POST',
      body: JSON.stringify({ ...payload, kind: 'ssh' }),
    })
    await loadWorkspaces()
    await selectWorkspace(ws.id)
  }

  async function removeWorkspace(id: string) {
    await api(`/api/workspaces/${id}`, { method: 'DELETE' })
    workspaces.value = workspaces.value.filter((w) => w.id !== id)
    if (workspaceId.value !== id) return
    const next = workspaces.value[0]
    if (next) {
      await selectWorkspace(next.id, { openExplorer: false })
      return
    }
    clearWorkspace()
  }

  async function updateWorkspace(
    id: string,
    payload: {
      name?: string
      root_path?: string
      ssh_display_name?: string
      ssh_host?: string
      ssh_port?: number
      ssh_user?: string
      ssh_password?: string
      ssh_private_key?: string
      ssh_passphrase?: string
    },
  ) {
    const ws = await api<Workspace>(`/api/workspaces/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
    await loadWorkspaces()
    if (workspaceId.value === id) {
      await selectWorkspace(id, { openExplorer: false })
    }
    return ws
  }

  function clearWorkspace() {
    stopWorkspaceStatusWatch()
    workspaceRootMissing.value = false
    detachRun()
    workspaceId.value = null
    localStorage.removeItem('ca.workspace')
    conversationId.value = null
    messages.value = []
    conversations.value = []
    openFiles.value = []
    activePath.value = null
    reviews.value = {}
    activeReviewIndex.value = {}
    confirmDialog.value = null
    fileTree.value = []
    childrenMap.value = {}
    expanded.value = new Set()
    treePath.value = ''
    gitChangedPaths.value = {}
    gitRepoOk.value = false
    gitCommitDraft.value = ''
    gitEditorDiff.value = {}
    sessionTreeMarks.value = {}
    ackedTreeMarks.value = {}
    fsClipboard.value = null
    fsUndoStack.value = []
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

  function editorTabsStorageKey(wsId: string) {
    return `ca.editor.tabs.${wsId}`
  }

  function editorActiveStorageKey(wsId: string) {
    return `ca.editor.active.${wsId}`
  }

  function readEditorTabs(wsId: string) {
    try {
      const raw = localStorage.getItem(editorTabsStorageKey(wsId))
      const parsed = raw ? JSON.parse(raw) : []
      return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string' && item.length > 0) : []
    } catch {
      return []
    }
  }

  function persistEditorState() {
    if (suppressEditorPersist.value) return
    const ws = workspaceId.value
    if (!ws) return
    const paths = openFiles.value.map((f) => f.path)
    localStorage.setItem(editorTabsStorageKey(ws), JSON.stringify(paths.slice(0, 40)))
    if (activePath.value) localStorage.setItem(editorActiveStorageKey(ws), activePath.value)
    else localStorage.removeItem(editorActiveStorageKey(ws))
  }

  async function restoreEditorState() {
    const ws = workspaceId.value
    if (!ws) return
    const tabs = readEditorTabs(ws)
    if (!tabs.length) return
    const savedActive = localStorage.getItem(editorActiveStorageKey(ws))
    for (const path of tabs) {
      if (openFiles.value.some((f) => f.path === path)) continue
      try {
        await openPath(path, false)
      } catch {
        /* file removed */
      }
    }
    if (savedActive && openFiles.value.some((f) => f.path === savedActive)) {
      activePath.value = savedActive
    } else if (openFiles.value.length) {
      activePath.value = openFiles.value[openFiles.value.length - 1].path
    }
    if (activePath.value) window.dispatchEvent(new Event('ca-focus-editor'))
  }

  async function selectWorkspace(
    id: string,
    opts?: { openExplorer?: boolean; conversationId?: string | null },
  ) {
    const gen = ++switchLoadGen
    switchLoading.value = t('workspace.switching')
    try {
      const opened = await api<Workspace & { root_missing?: boolean; plugins?: unknown }>(
        `/api/workspaces/${id}/open`,
        { method: 'POST' },
      )
      workspaceId.value = id
      localStorage.setItem('ca.workspace', id)
      const missingOnOpen = Boolean(opened.root_missing)
      workspaceRootMissing.value = missingOnOpen
      // Drop previous workspace chat immediately so the UI never keeps showing
      // remote/local messages from the workspace we just left.
      detachRun()
      conversationId.value = null
      messages.value = []
      reviews.value = {}
      activeReviewIndex.value = {}
      applied.value = new Set()
      suppressEditorPersist.value = true
      openFiles.value = []
      activePath.value = null
      const savedExpanded = readExpanded(id)
      treePath.value = ''
      childrenMap.value = {}
      expanded.value = new Set()
      gitChangedPaths.value = {}
      gitRepoOk.value = false
      gitCommitDraft.value = ''
      gitEditorDiff.value = {}
      sessionTreeMarks.value = {}
      ackedTreeMarks.value = {}
      fsClipboard.value = null
      fsUndoStack.value = []
      // Critical path first — git / editor restore are deferred so chat UI unlocks sooner.
      await Promise.all([
        loadConversations(),
        loadTree('').catch(() => {
          if (workspaceId.value !== id) return
          fileTree.value = []
          childrenMap.value = { ...childrenMap.value, '': [] }
        }),
        loadSkills(),
        loadProviders(),
      ])
      if (workspaceId.value !== id || gen !== switchLoadGen) return
      void loadGitChangedPaths()
      const expandTask = restoreExpandedDirs(savedExpanded)
      const preferred = opts?.conversationId
      const saved = localStorage.getItem(conversationStorageKey(id))
      const restore =
        (preferred && conversations.value.some((c) => c.id === preferred) && preferred) ||
        (saved && conversations.value.some((c) => c.id === saved) && saved) ||
        conversations.value[0]?.id ||
        null
      if (restore) {
        await openConversation(restore, { loading: false })
      } else {
        await newChat()
      }
      if (workspaceId.value !== id || gen !== switchLoadGen) return
      await expandTask
      void restoreEditorState().finally(() => {
        suppressEditorPersist.value = false
        persistEditorState()
      })
      if (opts?.openExplorer !== false) openExplorerPanel()
      void loadWorkspaces().then(() => {
        patchWorkspaceStatus(id, missingOnOpen)
      })
      startWorkspaceStatusWatch()
    } finally {
      if (gen === switchLoadGen) switchLoading.value = null
    }
  }

  async function loadTree(path = '') {
    if (!workspaceId.value) return
    const ws = workspaceId.value
    const data = await api<{ items: typeof fileTree.value }>(
      `/api/workspaces/${workspaceId.value}/tree?path=${encodeURIComponent(path)}`,
    )
    if (workspaceId.value !== ws) return
    // Merge atomically so parallel restores don't drop siblings.
    childrenMap.value = { ...childrenMap.value, [path]: data.items }
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
    const sorted = [...new Set(paths)]
      .sort((a, b) => depthOf(a) - depthOf(b) || a.localeCompare(b))
      .slice(0, 24)
    const kept = new Set<string>()
    const byDepth = new Map<number, string[]>()
    for (const path of sorted) {
      const d = depthOf(path)
      const bucket = byDepth.get(d) || []
      bucket.push(path)
      byDepth.set(d, bucket)
    }
    for (const depth of [...byDepth.keys()].sort((a, b) => a - b)) {
      const batch = (byDepth.get(depth) || []).filter((path) => {
        const parent = parentPath(path)
        return !parent || kept.has(parent)
      })
      if (!batch.length) continue
      await Promise.all(
        batch.map(async (path) => {
          const parent = parentPath(path)
          try {
            await loadTree(path)
          } catch {
            return
          }
          if (childrenOf(parent).some((item) => item.is_dir && item.path === path)) kept.add(path)
        }),
      )
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

  async function loadGitChangedPaths() {
    if (!workspaceId.value) {
      gitChangedPaths.value = {}
      gitRepoOk.value = false
      return
    }
    try {
      const status = await api<{ ok: boolean; files: { path: string; code: string }[] }>(
        `/api/workspaces/${workspaceId.value}/git/status`,
      )
      if (!status.ok) {
        gitChangedPaths.value = {}
        gitRepoOk.value = false
        return
      }
      gitRepoOk.value = true
      const next: Record<string, GitPathMark> = {}
      for (const file of status.files) {
        next[file.path] = { kind: gitMarkKind(file.code), code: file.code.trim() }
      }
      const prev = gitChangedPaths.value
      const same =
        Object.keys(next).length === Object.keys(prev).length &&
        Object.keys(next).every((path) => {
          const mark = prev[path]
          return mark && mark.kind === next[path].kind && mark.code === next[path].code
        })
      if (!same) gitChangedPaths.value = next
      if (Object.keys(next).length) {
        const session = { ...sessionTreeMarks.value }
        for (const path of Object.keys(next)) delete session[path]
        sessionTreeMarks.value = session
      }
    } catch {
      gitChangedPaths.value = {}
      gitRepoOk.value = false
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
    if (openFiles.value.some((f) => f.path === from || f.path.startsWith(`${from}/`))) {
      openFiles.value = openFiles.value.map((f) => {
        if (f.path !== from && !f.path.startsWith(`${from}/`)) return f
        const nextPath = f.path === from ? to : `${to}${f.path.slice(from.length)}`
        const next: typeof f = { ...f, path: nextPath }
        if (isPreviewKind(f.kind) && workspaceId.value) {
          next.previewUrl = rawFileUrl(workspaceId.value, nextPath)
        }
        return next
      })
      if (activePath.value === from || activePath.value?.startsWith(`${from}/`)) {
        activePath.value =
          activePath.value === from ? to : `${to}${activePath.value!.slice(from.length)}`
      }
    }
    const session = { ...sessionTreeMarks.value }
    for (const key of Object.keys(session)) {
      if (key === from || key.startsWith(`${from}/`)) {
        const nextKey = key === from ? to : `${to}${key.slice(from.length)}`
        session[nextKey] = session[key]
        delete session[key]
      }
    }
    sessionTreeMarks.value = session
    await loadTree(parentPath(from) || '')
    await loadTree(parentPath(to) || '')
    void loadGitChangedPaths()
  }

  async function copyEntry(from: string, to: string) {
    if (!workspaceId.value) return
    await api(`/api/workspaces/${workspaceId.value}/copy`, {
      method: 'POST',
      body: JSON.stringify({ path: from, new_path: to }),
    })
    await loadTree(parentPath(to) || '')
    const parent = parentPath(to)
    if (parent) setExpanded(new Set([...expanded.value, parent]))
    sessionTreeMarks.value = { ...sessionTreeMarks.value, [to]: 'added' }
    void loadGitChangedPaths()
  }

  type FsClipboard = { mode: 'copy' | 'cut'; path: string; is_dir: boolean; workspace_id: string }
  const fsClipboard = ref<FsClipboard | null>(null)
  type FsUndoDelete = {
    path: string
    isDir: boolean
    trashPath?: string
    files?: { path: string; content: string }[]
  }
  const fsUndoStack = ref<FsUndoDelete[]>([])
  const canUndoFs = computed(() => fsUndoStack.value.length > 0)

  function pushFsUndo(item: FsUndoDelete) {
    fsUndoStack.value = [...fsUndoStack.value, item].slice(-20)
  }

  function setFsClipboard(mode: 'copy' | 'cut', item: { path: string; is_dir: boolean }) {
    if (!workspaceId.value || !item.path) {
      fsClipboard.value = null
      return
    }
    fsClipboard.value = {
      mode,
      path: item.path,
      is_dir: item.is_dir,
      workspace_id: workspaceId.value,
    }
  }

  function clearFsClipboard() {
    fsClipboard.value = null
  }

  function uniqueChildPath(dir: string, name: string): string {
    const base = joinPath(dir, name)
    if (!childrenOf(dir).some((i) => i.path === base)) return base
    const dot = name.lastIndexOf('.')
    const hasExt = !name.startsWith('.') && dot > 0
    const stem = hasExt ? name.slice(0, dot) : name
    const ext = hasExt ? name.slice(dot) : ''
    for (let i = 1; i < 1000; i++) {
      const candidate = joinPath(dir, i === 1 ? `${stem} copy${ext}` : `${stem} copy ${i}${ext}`)
      if (!childrenOf(dir).some((item) => item.path === candidate)) return candidate
    }
    return joinPath(dir, `${stem} copy ${Date.now()}${ext}`)
  }

  async function pasteFsClipboard(destDir: string) {
    const clip = fsClipboard.value
    if (!clip || !workspaceId.value || clip.workspace_id !== workspaceId.value) return null
    const src = clip.path
    const name = src.split('/').filter(Boolean).pop() || src
    // Pasting a folder into itself / descendant is invalid.
    if (clip.is_dir && (destDir === src || destDir.startsWith(`${src}/`))) {
      throw new Error('Cannot paste into itself')
    }
    await loadTree(destDir)
    let dest = uniqueChildPath(destDir, name)
    // When cutting into the same directory with unique name, still ok (creates "copy" name only on conflict).
    // If cut and same parent and name free... uniqueChildPath returns same path if free - moving onto itself is no-op.
    if (clip.mode === 'cut' && dest === src) {
      clearFsClipboard()
      return src
    }
    if (clip.mode === 'copy') {
      await copyEntry(src, dest)
    } else {
      // If unique renamed due to conflict while cutting, rename to that path.
      await renameEntry(src, dest)
      clearFsClipboard()
    }
    if (destDir) setExpanded(new Set([...expanded.value, destDir]))
    return dest
  }

  /** Move a file/dir into destDir (workspace-relative). No-op if already there. */
  async function moveFsEntry(src: string, destDir: string, isDir: boolean) {
    if (!workspaceId.value || !src) return null
    if (isDir && (destDir === src || destDir.startsWith(`${src}/`))) {
      throw new Error('Cannot move into itself')
    }
    if (parentPath(src) === destDir) return src
    const name = src.split('/').filter(Boolean).pop() || src
    await loadTree(destDir)
    const dest = uniqueChildPath(destDir, name)
    if (dest === src) return src
    await renameEntry(src, dest)
    if (destDir) setExpanded(new Set([...expanded.value, destDir]))
    return dest
  }

  async function deleteEntry(relPath: string, isDir = false) {
    if (!workspaceId.value) return
    const name = relPath.split('/').filter(Boolean).pop() || relPath
    const trashPath = `.code-agent/data/trash/${crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}/${name}`
    let undo: FsUndoDelete | null = null
    try {
      await api(`/api/workspaces/${workspaceId.value}/copy`, {
        method: 'POST',
        body: JSON.stringify({ path: relPath, new_path: trashPath }),
      })
      undo = { path: relPath, isDir, trashPath }
    } catch {
      if (!isDir) {
        try {
          const open = openFiles.value.find((f) => f.path === relPath)
          const content =
            open && typeof open.content === 'string'
              ? open.content
              : (
                  await api<{ content: string }>(
                    `/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(relPath)}`,
                  )
                ).content
          undo = { path: relPath, isDir: false, files: [{ path: relPath, content }] }
        } catch {
          undo = null
        }
      }
    }
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
    if (undo) {
      pushFsUndo(undo)
      toast.info(t('explorer.deletedUndo', { path: relPath }), 6200)
    }
  }

  async function undoFsDelete() {
    const item = fsUndoStack.value.at(-1)
    if (!item || !workspaceId.value) return
    fsUndoStack.value = fsUndoStack.value.slice(0, -1)
    const parent = parentPath(item.path)
    await loadTree(parent)
    let dest = item.path
    const name = item.path.split('/').filter(Boolean).pop() || item.path
    if (childrenOf(parent).some((entry) => entry.path === item.path)) {
      dest = uniqueChildPath(parent, name)
    }
    try {
      if (item.trashPath) {
        await api(`/api/workspaces/${workspaceId.value}/rename`, {
          method: 'POST',
          body: JSON.stringify({ path: item.trashPath, new_path: dest }),
        })
        const trashRoot = item.trashPath.split('/').slice(0, 4).join('/')
        if (trashRoot.startsWith('.code-agent/data/trash/')) {
          await api(`/api/workspaces/${workspaceId.value}/entries?path=${encodeURIComponent(trashRoot)}`, {
            method: 'DELETE',
          }).catch(() => undefined)
        }
      } else {
        for (const file of item.files || []) {
          const target = file.path === item.path ? dest : file.path
          await writeWorkspaceFile(target, file.content)
        }
      }
      await loadTree(parent)
      if (item.isDir) {
        setExpanded(new Set([...expanded.value, dest].filter(Boolean)))
        await loadTree(dest).catch(() => undefined)
      } else {
        await openPath(dest, false)
      }
      void loadGitChangedPaths()
      toast.info(t('explorer.restored', { path: dest }))
    } catch (err) {
      pushFsUndo(item)
      toast.error(err instanceof Error ? err.message : t('explorer.restoreFail'))
    }
  }

  async function openPath(path: string, isDir: boolean) {
    if (isDir) {
      await toggleDir(path)
      return
    }
    const existing = openFiles.value.find((f) => f.path === path)
    const activeReview = pendingReview(path)
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
            if (activeReview) {
              existing.content = activeReview.after
              window.dispatchEvent(new CustomEvent('ca-file-reload', { detail: { path, content: activeReview.after } }))
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
      } else if (activeReview) {
        openFiles.value = [...openFiles.value, { path, kind: 'text', content: activeReview.after, dirty: false }]
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
    terminalCopyContext.value = null
  }

  function clearEditorCopyContext() {
    editorCopyContext.value = null
  }

  function setTerminalCopyContext(ctx: { text: string; startLine: number; endLine: number; title: string }) {
    terminalCopyContext.value = ctx
    editorCopyContext.value = null
  }

  function clearTerminalCopyContext() {
    terminalCopyContext.value = null
  }

  async function openChatFilePath(rawPath: string, line?: number) {
    if (!rawPath) return
    const root = workspace.value?.root_path || ''
    const ref = parseChatFileRef(rawPath, root)
    const path = ref?.openPath || rawPath
    const targetLine = line ?? ref?.line
    const revealRel = ref?.revealRel ?? null

    if (revealRel) {
      activity.value = 'explorer'
      window.dispatchEvent(new Event('ca-open-explorer'))
      await revealInTree(revealRel)
      if (targetLine) await openPathAtLine(revealRel, targetLine)
      else await openPath(revealRel, false)
      return
    }

    if (targetLine) await openPathAtLine(path, targetLine)
    else await openPath(path, false)
  }

  async function openAgentFile(path: string) {
    await openChatFilePath(path)
  }

  function clearGitEditorDiff(path?: string | null) {
    if (!path) {
      gitEditorDiff.value = {}
      return
    }
    if (!(path in gitEditorDiff.value)) return
    const next = { ...gitEditorDiff.value }
    delete next[path]
    gitEditorDiff.value = next
  }

  async function openWorkingDiff(relPath: string) {
    if (!workspaceId.value || !relPath) return
    let original = ''
    try {
      const data = await api<{ content: string }>(
        `/api/workspaces/${workspaceId.value}/git/blob?path=${encodeURIComponent(relPath)}&rev=HEAD`,
      )
      original = data.content ?? ''
    } catch {
      original = ''
    }
    await openPath(relPath, false)
    if (!openFiles.value.some((f) => f.path === relPath)) {
      openFiles.value = [
        ...openFiles.value,
        {
          path: relPath,
          kind: 'text',
          content: '',
          dirty: false,
          readonly: gitChangedPaths.value[relPath]?.kind === 'deleted',
        },
      ]
      activePath.value = relPath
    }
    gitEditorDiff.value = { ...gitEditorDiff.value, [relPath]: { original } }
    window.dispatchEvent(new Event('ca-focus-editor'))
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

  function reviewsForPath(path: string) {
    return reviews.value[path] || []
  }

  function pendingReviewsForPath(path: string) {
    return reviewsForPath(path).filter((r) => r.status === 'pending')
  }

  function pendingReviewCount(path: string | null | undefined) {
    if (!path) return 0
    return pendingReviewsForPath(path).length
  }

  function activeReviewIndexFor(path: string | null | undefined) {
    if (!path) return 0
    const list = pendingReviewsForPath(path)
    if (!list.length) return 0
    return Math.min(activeReviewIndex.value[path] ?? 0, list.length - 1)
  }

  function clampReviewIndex(path: string) {
    const list = pendingReviewsForPath(path)
    if (!list.length) {
      if (path in activeReviewIndex.value) {
        const next = { ...activeReviewIndex.value }
        delete next[path]
        activeReviewIndex.value = next
      }
      return
    }
    const cur = activeReviewIndex.value[path] ?? 0
    activeReviewIndex.value = { ...activeReviewIndex.value, [path]: Math.min(cur, list.length - 1) }
  }

  function pendingReview(path: string | null | undefined) {
    if (!path) return null
    const list = pendingReviewsForPath(path)
    if (!list.length) return null
    return list[activeReviewIndexFor(path)] ?? null
  }

  const pendingReviews = computed(() => {
    const out: FileReview[] = []
    for (const list of Object.values(reviews.value)) {
      for (const review of list) {
        if (review.status === 'pending') out.push(review)
      }
    }
    return out
  })

  const pendingReviewPaths = computed(() => [...new Set(pendingReviews.value.map((r) => r.path))])

  function cycleFileReview(path: string, delta: number) {
    const list = pendingReviewsForPath(path)
    if (list.length < 2) return
    const cur = activeReviewIndexFor(path)
    const next = (cur + delta + list.length) % list.length
    activeReviewIndex.value = { ...activeReviewIndex.value, [path]: next }
  }

  async function acceptAllReviews() {
    const items = pendingReviews.value
    if (!items.length) return
    for (const item of [...pendingReviews.value]) await acceptReview(item.path, item.blockId)
    await loadGitChangedPaths()
    if (gitRepoOk.value && Object.keys(gitChangedPaths.value).length) {
      const paths = Object.keys(gitChangedPaths.value)
      const message = draftCommitFromPaths(paths, t('editor.commitDraftDefault'))
      gitCommitDraft.value = message
      window.dispatchEvent(
        new CustomEvent('ca-git-commit-draft', {
          detail: { message },
        }),
      )
      window.dispatchEvent(new Event('ca-open-git'))
    }
  }

  async function rejectAllReviews() {
    const items = pendingReviews.value
    if (!items.length) return
    const paths = [...new Set(items.map((item) => item.path))]
    for (const item of [...pendingReviews.value]) await rejectReview(item.path, item.blockId)
    toast.info(t('editor.reviewRejectedAll', { n: paths.length }))
  }

  async function cycleReviewPath(delta: number) {
    const path = activePath.value
    const paths = pendingReviewPaths.value
    if (paths.length < 2) return
    const i = paths.indexOf(path || '')
    const start = i < 0 ? (delta > 0 ? -1 : 0) : i
    const next = paths[(start + delta + paths.length) % paths.length]
    await openAgentFile(next)
  }

  function ackedReviewStorageKey() {
    const ws = workspaceId.value
    return ws ? `ca.review.acked.${ws}` : ''
  }

  function readAckedReviewIds() {
    const key = ackedReviewStorageKey()
    if (!key) return new Set<string>()
    try {
      const raw = localStorage.getItem(key)
      const parsed = raw ? JSON.parse(raw) : []
      return new Set(Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [])
    } catch {
      return new Set<string>()
    }
  }

  function markReviewAcked(blockId: string) {
    const key = ackedReviewStorageKey()
    if (!key || !blockId) return
    const set = readAckedReviewIds()
    set.add(blockId)
    localStorage.setItem(key, JSON.stringify([...set].slice(-2000)))
  }

  function rebuildReviewsFromMessages(msgs: ChatMessage[]) {
    const acked = readAckedReviewIds()
    const next: Record<string, FileReview[]> = {}
    for (const msg of msgs) {
      for (const block of msg.blocks || []) {
        if (block.type !== 'file.diff' && block.type !== 'file.delete') continue
        const path = String(block.meta?.path || '')
        if (!path || acked.has(block.id)) continue
        const before = typeof block.meta.before === 'string' ? block.meta.before : null
        const after = typeof block.meta.after === 'string' ? block.meta.after : null
        if (before === null && after === null) continue
        const review: FileReview = {
          path,
          action: String(block.meta.action || (block.type === 'file.delete' ? 'delete' : 'edit')),
          before: before ?? '',
          after: after ?? '',
          status: 'pending',
          blockId: block.id,
        }
        const list = next[path] || []
        if (!list.some((item) => item.blockId === block.id)) list.push(review)
        next[path] = list
      }
    }
    reviews.value = next
    activeReviewIndex.value = {}
  }

  function upsertReview(block: { id: string; type: string; meta: Record<string, unknown> }) {
    if (block.type !== 'file.diff' && block.type !== 'file.delete') return
    const path = String(block.meta.path || '')
    if (!path) return
    const before = typeof block.meta.before === 'string' ? block.meta.before : null
    const after = typeof block.meta.after === 'string' ? block.meta.after : null
    if (before === null && after === null) return
    const entry: FileReview = {
      path,
      action: String(block.meta.action || (block.type === 'file.delete' ? 'delete' : 'edit')),
      before: before ?? '',
      after: after ?? '',
      status: 'pending',
      blockId: block.id,
    }
    const list = reviewsForPath(path)
    const i = list.findIndex((item) => item.blockId === block.id)
    let nextList: FileReview[]
    if (i >= 0) {
      nextList = [...list]
      nextList[i] = entry
    } else {
      nextList = [...list, entry]
      const pendingCount = nextList.filter((item) => item.status === 'pending').length
      activeReviewIndex.value = { ...activeReviewIndex.value, [path]: pendingCount - 1 }
    }
    reviews.value = { ...reviews.value, [path]: nextList }
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

  async function writeWorkspaceFile(path: string, content: string) {
    if (!workspaceId.value) return
    await api(`/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(path)}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    })
    await syncOpenFile(path, content, false)
  }

  async function uploadWorkspaceFile(
    relPath: string,
    file: File,
    onByteProgress?: (loaded: number, total: number) => void,
  ) {
    if (!workspaceId.value) throw new Error('No workspace')
    const form = new FormData()
    form.append('file', file, file.name)
    const url = `/api/workspaces/${workspaceId.value}/upload?path=${encodeURIComponent(relPath)}`

    return await new Promise<{ ok: boolean; path: string; size: number }>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', url)
      xhr.responseType = 'json'
      xhr.upload.onprogress = (ev) => {
        if (!ev.lengthComputable) return
        onByteProgress?.(ev.loaded, ev.total)
      }
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const body = xhr.response || {}
          resolve({
            ok: Boolean(body.ok ?? true),
            path: String(body.path || relPath),
            size: Number(body.size ?? file.size),
          })
          return
        }
        let msg = xhr.statusText || 'Upload failed'
        try {
          const raw = typeof xhr.response === 'string' ? xhr.response : JSON.stringify(xhr.response)
          const parsed = typeof xhr.response === 'object' && xhr.response ? xhr.response : JSON.parse(raw || '{}')
          msg =
            typeof parsed === 'string'
              ? parsed
              : JSON.stringify((parsed as { detail?: unknown }).detail || parsed) || msg
        } catch {
          /* keep statusText */
        }
        reject(new Error(msg))
      }
      xhr.onerror = () => reject(new Error('Upload failed'))
      xhr.onabort = () => reject(new Error('Upload aborted'))
      xhr.send(form)
    })
  }

  function planWorkspaceUploadPaths(destDir: string, files: File[]): { file: File; rel: string; label: string }[] {
    const planned: { file: File; relRaw: string }[] = []
    for (const file of files) {
      const relRaw = fileRelativePath(file)
      if (!relRaw) continue
      planned.push({ file, relRaw })
    }
    if (!planned.length) return []

    const topNames = [...new Set(planned.map((p) => p.relRaw.split('/')[0]!))]
    const renameTop = new Map<string, string>()
    for (const name of topNames) {
      const unique = uniqueChildPath(destDir, name)
      const uniqueName = unique.split('/').filter(Boolean).pop() || name
      if (uniqueName !== name) renameTop.set(name, uniqueName)
    }

    return planned.map(({ file, relRaw }) => {
      const parts = relRaw.split('/')
      const top = parts[0]!
      if (renameTop.has(top)) parts[0] = renameTop.get(top)!
      const rel = joinPath(destDir, parts.join('/'))
      return { file, rel, label: parts.join('/') }
    })
  }

  async function uploadWorkspaceFiles(
    destDir: string,
    files: FileList | File[],
    onProgress?: (info: { current: number; total: number; name: string; ratio: number }) => void,
  ) {
    if (!workspaceId.value) return []
    const list = Array.from(files).filter((f) => f && f.name)
    if (!list.length) return []
    const UPLOAD_MAX_FILES = 2000
    if (list.length > UPLOAD_MAX_FILES) {
      throw new Error(t('explorer.uploadTooMany', { max: UPLOAD_MAX_FILES }))
    }
    if (destDir) await expandDir(destDir)
    else await loadTree('')

    const planned = planWorkspaceUploadPaths(destDir, list)
    if (!planned.length) return []

    const weights = planned.map((p) => Math.max(p.file.size, 1))
    const totalWeight = weights.reduce((sum, n) => sum + n, 0)
    let doneWeight = 0
    const uploaded: string[] = []
    const total = planned.length

    for (let i = 0; i < planned.length; i++) {
      const { file, rel, label } = planned[i]
      const weight = weights[i]
      await uploadWorkspaceFile(rel, file, (loaded, totalBytes) => {
        const part = Math.min(1, loaded / Math.max(totalBytes || weight, 1))
        onProgress?.({
          current: i + 1,
          total,
          name: label,
          ratio: Math.min(0.999, (doneWeight + part * weight) / totalWeight),
        })
      })
      doneWeight += weight
      sessionTreeMarks.value = { ...sessionTreeMarks.value, [rel]: 'added' }
      uploaded.push(rel)
      onProgress?.({
        current: i + 1,
        total,
        name: label,
        ratio: Math.min(1, doneWeight / totalWeight),
      })
    }
    await loadTree(destDir || '')
    if (destDir) await expandDir(destDir)
    return uploaded
  }

  function patchReview(path: string, blockId: string, patch: Partial<FileReview>) {
    reviews.value = {
      ...reviews.value,
      [path]: reviewsForPath(path).map((item) => (item.blockId === blockId ? { ...item, ...patch } : item)),
    }
  }

  function setReviewStatus(path: string, blockId: string, status: 'accepted' | 'rejected') {
    reviews.value = {
      ...reviews.value,
      [path]: reviewsForPath(path).map((item) => (item.blockId === blockId ? { ...item, status } : item)),
    }
    clampReviewIndex(path)
  }

  async function applyAgentFileUpdate(path: string, content: string) {
    const file = openFiles.value.find((f) => f.path === path)
    if (!file) return
    if (!file.dirty) {
      file.content = content
      window.dispatchEvent(new CustomEvent('ca-file-reload', { detail: { path, content } }))
      return
    }
    const useAgent = await askConfirm({
      title: t('editor.agentWriteConflictTitle'),
      summary: t('editor.agentWriteConflictSummary', { path }),
      confirmLabel: t('editor.useAgentVersion'),
      cancelLabel: t('editor.keepMine'),
      danger: false,
    })
    if (useAgent) await syncOpenFile(path, content, false)
  }

  async function acceptReview(path: string, blockId?: string) {
    const review = blockId
      ? pendingReviewsForPath(path).find((item) => item.blockId === blockId)
      : pendingReview(path)
    if (!review || review.status !== 'pending') return
    setReviewStatus(path, review.blockId, 'accepted')
    markReviewAcked(review.blockId)
    await writeWorkspaceFile(path, review.after)
    if (!pendingReviewsForPath(path).length) {
      const session = { ...sessionTreeMarks.value }
      delete session[path]
      sessionTreeMarks.value = session
      ackedTreeMarks.value = { ...ackedTreeMarks.value, [path]: true }
    }
    void loadGitChangedPaths()
  }

  async function acceptReviewHunk(
    path: string,
    change: {
      originalStartLineNumber: number
      originalEndLineNumber: number
      modifiedStartLineNumber: number
      modifiedEndLineNumber: number
    },
    blockId?: string,
  ) {
    const review = blockId
      ? pendingReviewsForPath(path).find((item) => item.blockId === blockId)
      : pendingReview(path)
    if (!review || review.status !== 'pending') return
    const nextBefore = acceptHunkIntoBefore(review.before, review.after, change)
    if (textsEqual(nextBefore, review.after)) {
      await acceptReview(path, review.blockId)
      return
    }
    patchReview(path, review.blockId, { before: nextBefore })
    await writeWorkspaceFile(path, nextBefore)
    void loadGitChangedPaths()
  }

  async function rejectReviewHunk(
    path: string,
    change: {
      originalStartLineNumber: number
      originalEndLineNumber: number
      modifiedStartLineNumber: number
      modifiedEndLineNumber: number
    },
    blockId?: string,
  ) {
    const review = blockId
      ? pendingReviewsForPath(path).find((item) => item.blockId === blockId)
      : pendingReview(path)
    if (!review || review.status !== 'pending') return
    const nextAfter = rejectHunkFromAfter(review.before, review.after, change)
    if (textsEqual(nextAfter, review.before)) {
      await rejectReview(path, review.blockId)
      return
    }
    patchReview(path, review.blockId, { after: nextAfter })
    await writeWorkspaceFile(path, nextAfter)
    void loadGitChangedPaths()
  }

  async function rejectReview(path: string, blockId?: string, opts?: { silent?: boolean }) {
    const review = blockId
      ? pendingReviewsForPath(path).find((item) => item.blockId === blockId)
      : pendingReview(path)
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
      if (!pendingReviewsForPath(path).filter((item) => item.blockId !== review.blockId).length) {
        closeFile(path)
      }
      await loadTree(parentPath(path) || '')
    } else {
      await api(`/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(path)}`, {
        method: 'PUT',
        body: JSON.stringify({ content: review.before }),
      })
      await syncOpenFile(path, review.before, false)
    }
    setReviewStatus(path, review.blockId, 'rejected')
    markReviewAcked(review.blockId)
    void loadGitChangedPaths()
    if (!opts?.silent) toast.info(t('editor.reviewRejected', { path }))
  }

  function pendingReviewsForMessage(msg: ChatMessage) {
    const ids = new Set((msg.blocks || []).map((block) => block.id))
    return pendingReviews.value.filter((item) => ids.has(item.blockId))
  }

  async function rejectReviewsForMessage(msg: ChatMessage) {
    const items = pendingReviewsForMessage(msg)
    if (!items.length) return
    const paths = [...new Set(items.map((item) => item.path))]
    for (const item of items) await rejectReview(item.path, item.blockId, { silent: true })
    toast.info(t('chat.runRejected', { n: paths.length }))
  }

  async function acceptReviewsForMessage(msg: ChatMessage) {
    const items = pendingReviewsForMessage(msg)
    if (!items.length) return
    for (const item of items) await acceptReview(item.path, item.blockId)
    toast.info(t('chat.runAccepted', { n: items.length }))
  }

  function activateFile(path: string) {
    if (openFiles.value.some((f) => f.path === path)) activePath.value = path
  }

  function closeFile(path: string) {
    const i = openFiles.value.findIndex((f) => f.path === path)
    if (i < 0) return
    const next = openFiles.value.filter((f) => f.path !== path)
    openFiles.value = next
    clearGitEditorDiff(path)
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

  function closeFilesToTheLeft(path: string) {
    const i = openFiles.value.findIndex((f) => f.path === path)
    if (i <= 0) return
    openFiles.value = openFiles.value.slice(i)
    if (!openFiles.value.some((f) => f.path === activePath.value)) activePath.value = path
  }

  function closeAllFiles() {
    openFiles.value = []
    activePath.value = null
    gitEditorDiff.value = {}
  }

  function reorderOpenFiles(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) return
    const list = [...openFiles.value]
    if (fromIndex >= list.length || toIndex >= list.length) return
    const [item] = list.splice(fromIndex, 1)
    list.splice(toIndex, 0, item)
    openFiles.value = list
  }

  function moveOpenFile(path: string, toIndex: number) {
    const from = openFiles.value.findIndex((f) => f.path === path)
    if (from < 0) return
    reorderOpenFiles(from, Math.max(0, Math.min(toIndex, openFiles.value.length - 1)))
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
    const rows = await api<Conversation[]>(`/api/workspaces/${workspaceId.value}/conversations`)
    const currentId = conversationId.value
    const current = conversations.value.find((c) => c.id === currentId)
    conversations.value = rows
    if (current?.archived && currentId && !rows.some((c) => c.id === currentId)) {
      conversations.value = [current, ...conversations.value]
    }
  }

  async function searchConversations(q: string, archived: 'exclude' | 'include' | 'only' = 'include') {
    if (!workspaceId.value) return [] as Conversation[]
    const params = new URLSearchParams()
    const query = q.trim()
    if (query) params.set('q', query)
    params.set('archived', archived)
    return api<Conversation[]>(`/api/workspaces/${workspaceId.value}/conversations?${params}`)
  }

  async function archiveConversation(id: string, archived = true) {
    const data = await api<Conversation>(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ archived }),
    })
    if (archived) {
      conversations.value = conversations.value
        .map((c) => (c.id === id ? { ...c, ...data, archived: true } : c))
        .filter((c) => !c.archived || c.id === conversationId.value)
    } else {
      await loadConversations()
      conversations.value = conversations.value.map((c) => (c.id === id ? { ...c, ...data, archived: false } : c))
    }
    return data
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
        void applyAgentFileUpdate(changedPath, meta.after)
      }
      if (type === 'file.diff' && (meta.action === 'create' || meta.action === 'overwrite') && changedPath) {
        if (meta.action === 'create') {
          sessionTreeMarks.value = { ...sessionTreeMarks.value, [changedPath]: 'added' }
        }
      }
    }
    if (event.type === 'run.started') {
      runStatus.value = 'running'
      syncCurrentConversationStatus({ awaiting_approval: false })
    }
    if (event.type === 'block.started' && type === 'approval') {
      notifyApprovalRequired(String(meta.approval_id || blockId || ''))
      syncCurrentConversationStatus({ awaiting_approval: true })
    }
    if (event.type === 'run.completed') {
      playTaskCompleteSound()
    }
    if (event.type === 'run.completed' || event.type === 'run.failed' || event.type === 'run.cancelled') {
      runStatus.value = event.type.replace('run.', '')
      const now = new Date().toISOString()
      const decision = event.type === 'run.cancelled' ? 'cancelled' : 'denied'
      messages.value = settleUndecidedApprovals(
        messages.value.map((m) => (m.run_id === event.run_id ? { ...m, ended_at: now } : m)),
        { runId: event.run_id, decision },
      )
      void refreshTree()
      if (activeRunId.value === event.run_id) activeRunId.value = null
      streamConnection.value = 'idle'
      streamResumeAfter = null
      syncCurrentConversationStatus({ awaiting_approval: false })
      void flushSendQueue()
    }
    if (event.type === 'block.started' || event.type === 'block.completed') {
      const name = String((meta as { name?: string }).name || '')
      const fileOp =
        type.startsWith('file.') ||
  ['write_file', 'search_replace', 'apply_patch', 'delete_file', 'read_file'].includes(name)
      if (fileOp) scheduleTreeRefresh(path || undefined)
    }
  }

  function patchConversationStatus(
    id: string | null | undefined,
    patch: Partial<Pick<Conversation, 'active_run_id' | 'run_status' | 'awaiting_approval' | 'turn_count' | 'updated_at'>>,
  ) {
    if (!id) return
    conversations.value = conversations.value.map((c) => (c.id === id ? { ...c, ...patch } : c))
  }

  function syncCurrentConversationStatus(extra?: Partial<Pick<Conversation, 'awaiting_approval'>>) {
    const id = conversationId.value
    if (!id) return
    const busy = runStatus.value === 'running' || runStatus.value === 'queued' || Boolean(activeRunId.value)
    const awaiting =
      extra?.awaiting_approval ??
      (busy && pendingApprovalsFromMessages(messages.value).length > 0)
    patchConversationStatus(id, {
      active_run_id: activeRunId.value,
      run_status: busy ? runStatus.value || 'running' : null,
      awaiting_approval: Boolean(awaiting),
    })
  }

  function detachRun() {
    discardPendingDeltas()
    stopStream?.()
    stopStream = null
    activeRunId.value = null
    runStatus.value = 'idle'
    lastEventId.value = null
    streamConnection.value = 'idle'
    streamResumeAfter = null
  }

  async function openConversation(id: string, opts?: { loading?: boolean }) {
    const showLoading = opts?.loading !== false
    const gen = showLoading ? ++switchLoadGen : switchLoadGen
    if (showLoading) switchLoading.value = t('chat.loadingConversation')
    try {
      // Leave the previous run stream behind so the new chat is not "busy"
      detachRun()
      conversationId.value = id
      rememberConversation(id)
      conversations.value = conversations.value.filter((c) => !c.archived || c.id === id)
      reviews.value = {}
      activeReviewIndex.value = {}
      messages.value = []
      const data = await api<Conversation & { messages: ChatMessage[]; active_run: any }>(`/api/conversations/${id}`)
      // Ignore late responses if user already switched again
      if (conversationId.value !== id) return
      messages.value = data.messages || []
      rebuildReviewsFromMessages(messages.value)
      mode.value = (data.mode as typeof mode.value) || 'agent'
      modelId.value = data.model_id
      applied.value = new Set()
      const active = data.active_run
      if (active && ['queued', 'running'].includes(String(active.status))) {
        lastEventId.value = active.last_event_id
        attachRun(active.id, active.last_event_id)
        syncCurrentConversationStatus({
          awaiting_approval: pendingApprovalsFromMessages(messages.value).length > 0,
        })
      } else {
        // Stale approval cards from failed/cancelled runs must not keep the action bar open.
        messages.value = settleUndecidedApprovals(messages.value, { decision: 'denied' })
        runStatus.value = 'idle'
        activeRunId.value = null
        lastEventId.value = null
        syncCurrentConversationStatus({ awaiting_approval: false })
      }
      window.dispatchEvent(new Event('ca-messages-loaded'))
    } finally {
      if (showLoading && gen === switchLoadGen) switchLoading.value = null
    }
  }

  async function deleteConversation(id: string) {
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

  async function renameConversation(id: string, title: string) {
    const trimmed = title.trim()
    if (!trimmed) return false
    const row = conversations.value.find((c) => c.id === id)
    if (!row || row.title === trimmed) return true

    await api(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title: trimmed }),
    })
    conversations.value = conversations.value.map((c) =>
      c.id === id ? { ...c, title: trimmed } : c,
    )
    return true
  }

  async function rollbackToMessage(messageId: string, mode: 'to' | 'before' = 'to') {
    const id = conversationId.value
    if (!id) return null
    const result = await api<{
      ok: boolean
      messages_removed: number
      files_reverted: number
      reverted_paths: string[]
      warnings: string[]
    }>(`/api/conversations/${id}/rollback`, {
      method: 'POST',
      body: JSON.stringify({ message_id: messageId, mode }),
    })
    detachRun()
    const reverted = new Set(result.reverted_paths || [])
    for (const file of [...openFiles.value]) {
      if (!reverted.has(file.path)) continue
      try {
        await reloadOpenFile(file.path)
      } catch {
        closeFile(file.path)
      }
    }
    reviews.value = {}
    activeReviewIndex.value = {}
    await openConversation(id)
    await loadTree('')
    await loadConversations()
    await loadGitChangedPaths()
    return result
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
    if (!activeRunId.value || String(event.run_id) !== String(activeRunId.value)) return
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

  function onStreamConnection(runId: string, state: StreamConnectionState) {
    // Ignore stale callbacks after we've already moved on to another run.
    if (activeRunId.value !== runId) return
    if (state === 'live' || state === 'connecting') {
      if (streamConnection.value !== 'live') streamConnection.value = 'live'
      return
    }
    if (state === 'reconnecting') {
      streamConnection.value = 'reconnecting'
      return
    }
    // 'closed' from a finished stream — idle (terminal events also clear this)
    if (runStatus.value === 'running' || runStatus.value === 'queued') {
      streamConnection.value = 'disconnected'
    } else {
      streamConnection.value = 'idle'
    }
  }

  function attachRun(runId: string, after?: string | null) {
    discardPendingDeltas()
    stopStream?.()
    stopStream = null
    activeRunId.value = runId
    runStatus.value = 'running'
    streamResumeAfter = after || null
    streamConnection.value = 'live'
    // Fresh run should not inherit idempotency keys from a prior stream.
    if (!after) applied.value = new Set()
    syncCurrentConversationStatus({ awaiting_approval: false })
    const attachedRunId = runId
    stopStream = subscribeRun(
      runId,
      after || null,
      (event) => {
        if (activeRunId.value !== attachedRunId) return
        streamResumeAfter = event.event_id
        onEvent(event)
      },
      () => {
        // Prefer attachedRunId over activeRunId: applyIncomingEvent may already
        // have cleared activeRunId on the terminal event.
        if (activeRunId.value && activeRunId.value !== attachedRunId) return
        flushPendingDeltas()
        releaseHeldEvents()
        messages.value = settleUndecidedApprovals(messages.value, { runId: attachedRunId, decision: 'denied' })
        if (runStatus.value === 'running' || runStatus.value === 'queued') {
          runStatus.value = 'completed'
        }
        if (activeRunId.value === attachedRunId) activeRunId.value = null
        streamConnection.value = 'idle'
        streamResumeAfter = null
        syncCurrentConversationStatus({ awaiting_approval: false })
        loadConversations()
        void flushSendQueue()
      },
      (state) => onStreamConnection(attachedRunId, state),
    )
  }

  function reconnectActiveStream() {
    const runId = activeRunId.value
    if (!runId) {
      streamConnection.value = 'idle'
      return
    }
    attachRun(runId, streamResumeAfter || lastEventId.value)
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
    references: {
    type: string
    path: string
    text?: string
    line_start?: number
    line_end?: number
    title?: string
  }[] = [],
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
    references: {
    type: string
    path: string
    text?: string
    line_start?: number
    line_end?: number
    title?: string
  }[] = [],
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
    if (!hasConfiguredModel.value) {
      toast.warning(t('chat.needModel'))
      window.dispatchEvent(new Event('ca-open-models'))
      return
    }
    const sendMode = opts?.mode ?? mode.value
    const sendModel = opts?.modelId ?? modelId.value
    const sendThinking = opts?.thinkingLevel ?? thinkingLevel.value
    const sendSkill = opts?.skillName !== undefined ? opts.skillName : conversationSkillName()
    const localId = `local-${Date.now()}`
    messages.value = [
      ...messages.value,
      {
        id: localId,
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
    try {
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
    } catch (err) {
      messages.value = messages.value.filter((m) => m.id !== localId)
      toast.error(err instanceof Error ? err.message : t('chat.sendFailed'))
      throw err
    }
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
      toast.error(err instanceof Error ? err.message : t('chat.sendFailed'))
    } finally {
      queueFlushing = false
    }
  }

  async function send(
    text: string,
    references: {
    type: string
    path: string
    text?: string
    line_start?: number
    line_end?: number
    title?: string
  }[] = [],
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
    references: {
    type: string
    path: string
    text?: string
    line_start?: number
    line_end?: number
    title?: string
  }[] = [],
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
    try {
      await api(`/api/runs/${runId}/cancel`, { method: 'POST' })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('chat.stopFailed'))
    }
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
    const decision = allowed ? 'approved' : 'denied'
    messages.value = messages.value.map((msg) => {
      if (msg.role !== 'assistant') return msg
      let changed = false
      const blocks = msg.blocks.map((block) => {
        if (block.type !== 'approval') return block
        if (String(block.meta.approval_id || '') !== approvalId) return block
        changed = true
        return {
          ...block,
          status: allowed ? 'ok' : 'error',
          meta: { ...block.meta, decision },
        }
      })
      return changed ? { ...msg, blocks } : msg
    })
    syncCurrentConversationStatus()
    api(`/api/runs/${runId}/approvals/${approvalId}`, {
      method: 'POST',
      body: JSON.stringify({ allowed }),
    }).catch(() => undefined)
  }

  const pendingApprovals = computed(() => {
    // Only surface live confirmations for the in-flight run.
    if (!activeRunId.value) return []
    if (runStatus.value !== 'running' && runStatus.value !== 'queued') return []
    return pendingApprovalsFromMessages(messages.value)
  })

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

  const hasConfiguredModel = computed(() =>
    providers.value.some((p) => Array.isArray(p.models) && p.models.length > 0),
  )

  async function quickAddPreset(kind: string) {
    await api(`/api/llm/presets/${kind}`, {
      method: 'POST',
      body: JSON.stringify({ make_default: true }),
    })
    await loadProviders()
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

  const gitMarkedAncestorPaths = computed(() => {
    const out = new Set<string>()
    if (!gitRepoOk.value) return out
    const addAncestors = (path: string) => {
      const parts = path.split('/').filter(Boolean)
      let acc = ''
      for (let i = 0; i < parts.length - 1; i++) {
        acc = acc ? `${acc}/${parts[i]}` : parts[i]
        out.add(acc)
      }
    }
    for (const path of Object.keys(gitChangedPaths.value)) {
      addAncestors(path)
    }
    return out
  })

  function fileTreeMark(path: string, isDir = false): FileTreeMark {
    const empty: FileTreeMark = { show: false, title: '', kind: '' }

    const markFromGit = (git: GitPathMark): FileTreeMark => {
      const letter = gitMarkLetter(git.code)
      return {
        show: true,
        title: gitMarkTitle(git, path),
        kind: git.kind,
        ...(letter ? { letter } : {}),
      }
    }

    const dirtyMark = (): FileTreeMark | null => {
      if (isDir || !isFileDirty(path)) return null
      return { show: true, title: t('tree.unsaved'), kind: 'modified', letter: 'M' }
    }

    if (!gitRepoOk.value) return dirtyMark() ?? empty

    if (isDir) {
      const own = gitChangedPaths.value[path]
      if (own) return markFromGit(own)
      if (gitMarkedAncestorPaths.value.has(path)) {
        return { show: true, title: t('tree.containsChanges'), kind: 'changed' }
      }
      return empty
    }

    const git = gitChangedPaths.value[path]
    if (git) return markFromGit(git)
    return dirtyMark() ?? empty
  }

  watch(
    () => [workspaceId.value, openFiles.value.map((f) => f.path).join('\0'), activePath.value] as const,
    () => persistEditorState(),
  )

  return {
    workspaces,
    recentWorkspaces,
    workspaceId,
    workspace,
    workspaceRootMissing,
    refreshWorkspaceStatus,
    startWorkspaceStatusWatch,
    stopWorkspaceStatusWatch,
    conversations,
    conversationId,
    messages,
    switchLoading,
    runStatus,
    streamConnection,
    reconnectActiveStream,
    sendQueue,
    mode,
    modelId,
    hasConfiguredModel,
    quickAddPreset,
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
    terminalCopyContext,
    setTerminalCopyContext,
    clearTerminalCopyContext,
    fileNotice,
    clearFileNotice,
    pendingReveal,
    searchIntent,
    openSearch,
    openExplorerPanel,
    skillFocusIntent,
    openSkill,
    reviews,
    activeReviewIndex,
    pendingReview,
    pendingReviews,
    pendingReviewPaths,
    pendingReviewCount,
    activeReviewIndexFor,
    cycleFileReview,
    acceptAllReviews,
    rejectAllReviews,
    cycleReviewPath,
    confirmDialog,
    askConfirm,
    closeConfirm,
    decideApproval,
    pendingApprovals,
    providers,
    skills,
    conversationSkills,
    settings,
    activity,
    pendingModelProbe,
    loadWorkspaces,
    addWorkspace,
    addSshWorkspace,
    removeWorkspace,
    updateWorkspace,
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
    copyEntry,
    deleteEntry,
    canUndoFs,
    undoFsDelete,
    fsClipboard,
    setFsClipboard,
    clearFsClipboard,
    pasteFsClipboard,
    moveFsEntry,
    uploadWorkspaceFiles,
    openPath,
    openPathAtLine,
    openChatFilePath,
    openAgentFile,
    openWorkingDiff,
    clearGitEditorDiff,
    gitEditorDiff,
    openRevisionFile,
    acceptReview,
    acceptReviewHunk,
    rejectReviewHunk,
    rejectReview,
    pendingReviewsForMessage,
    rejectReviewsForMessage,
    acceptReviewsForMessage,
    activateFile,
    closeFile,
    closeOtherFiles,
    closeFilesToTheRight,
    closeFilesToTheLeft,
    closeAllFiles,
    reorderOpenFiles,
    moveOpenFile,
    updateOpenContent,
    saveOpenFile,
    reloadOpenFile,
    isFileDirty,
    fileTreeMark,
    gitRepoOk,
    gitCommitDraft,
    loadGitChangedPaths,
    gitChangedPaths,
    loadConversations,
    searchConversations,
    archiveConversation,
    newChat,
    openConversation,
    deleteConversation,
    renameConversation,
    rollbackToMessage,
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
