import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { api, subscribeRun, type StreamEnvelope } from '@/api/http'
import { applyEvent, type ChatMessage } from '@/protocol/applyEvent'

export type Workspace = { id: string; name: string; root_path: string }
export type Conversation = {
  id: string
  title: string
  mode: string
  model_id: string | null
  active_run_id: string | null
}

export type FsItem = { name: string; path: string; is_dir: boolean }
export type OpenFile = { path: string; content: string; dirty: boolean }
export type FileReview = {
  path: string
  action: string
  before: string
  after: string
  status: 'pending' | 'accepted' | 'rejected'
  blockId: string
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
  const thinking = ref(localStorage.getItem('ca.thinking') === '1')
  watch(thinking, (on) => localStorage.setItem('ca.thinking', on ? '1' : '0'))
  const fileTree = ref<FsItem[]>([])
  const childrenMap = ref<Record<string, FsItem[]>>({})
  const expanded = ref<Set<string>>(new Set())
  const treePath = ref('')
  const openFiles = ref<OpenFile[]>([])
  const activePath = ref<string | null>(null)
  const openFile = computed(() => openFiles.value.find((f) => f.path === activePath.value) || null)
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
  let confirmResolver: ((ok: boolean) => void) | null = null
  const providers = ref<any[]>([])
  const skills = ref<any[]>([])
  const settings = ref<{ schema: any; values: Record<string, unknown> } | null>(null)
  const activity = ref('files')
  let stopStream: (() => void) | null = null
  let treeTimer: ReturnType<typeof setTimeout> | null = null
  const pendingTreePaths = new Set<string>()

  const workspace = computed(() => workspaces.value.find((w) => w.id === workspaceId.value) || null)

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
    stopStream?.()
    workspaceId.value = null
    localStorage.removeItem('ca.workspace')
    conversationId.value = null
    messages.value = []
    conversations.value = []
    openFiles.value = []
    activePath.value = null
    reviews.value = {}
    confirmDialog.value = null
    activeRunId.value = null
    fileTree.value = []
    childrenMap.value = {}
    expanded.value = new Set()
    treePath.value = ''
    runStatus.value = 'idle'
  }

  async function selectWorkspace(id: string) {
    workspaceId.value = id
    localStorage.setItem('ca.workspace', id)
    treePath.value = ''
    childrenMap.value = {}
    expanded.value = new Set()
    await Promise.all([loadConversations(), loadTree(''), loadSkills(), loadProviders()])
    if (conversations.value[0]) {
      await openConversation(conversations.value[0].id)
    } else {
      await newChat()
    }
  }

  async function loadTree(path = '') {
    if (!workspaceId.value) return
    const data = await api<{ items: typeof fileTree.value }>(
      `/api/workspaces/${workspaceId.value}/tree?path=${encodeURIComponent(path)}`,
    )
    childrenMap.value = { ...childrenMap.value, [path]: data.items }
    if (!path) fileTree.value = data.items
    treePath.value = path
  }

  function isExpanded(path: string) {
    return expanded.value.has(path)
  }

  async function toggleDir(path: string) {
    const next = new Set(expanded.value)
    if (next.has(path)) {
      next.delete(path)
      expanded.value = next
      return
    }
    next.add(path)
    expanded.value = next
    await loadTree(path)
  }

  async function refreshTree() {
    await loadTree('')
    for (const path of [...expanded.value]) {
      await loadTree(path)
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
    await loadTree(parentPath(relPath) || '')
  }

  function scheduleTreeRefresh(relPath?: string) {
    if (relPath) pendingTreePaths.add(relPath)
    if (treeTimer) return
    treeTimer = setTimeout(async () => {
      treeTimer = null
      const paths = [...pendingTreePaths]
      pendingTreePaths.clear()
      if (!paths.length) {
        await refreshTree()
        return
      }
      for (const path of paths) await revealInTree(path)
    }, 250)
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
      expanded.value = new Set([...expanded.value, parentPath(relPath) || '', relPath])
      await loadTree(relPath)
    } else if (parentPath(relPath)) {
      expanded.value = new Set([...expanded.value, parentPath(relPath)])
    }
    if (kind === 'file') await openPath(relPath, false)
  }

  async function renameEntry(from: string, to: string) {
    if (!workspaceId.value) return
    await api(`/api/workspaces/${workspaceId.value}/rename`, {
      method: 'POST',
      body: JSON.stringify({ path: from, new_path: to }),
    })
    if (openFiles.value.some((f) => f.path === from)) {
      openFiles.value = openFiles.value.map((f) => (f.path === from ? { ...f, path: to } : f))
      if (activePath.value === from) activePath.value = to
    }
    await loadTree(parentPath(to) || '')
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
      expanded.value = next
    }
    await loadTree(parent)
  }

  async function openPath(path: string, isDir: boolean) {
    if (isDir) {
      await toggleDir(path)
      return
    }
    const existing = openFiles.value.find((f) => f.path === path)
    const review = reviews.value[path]
    if (existing) {
      if (!existing.dirty && workspaceId.value) {
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
      activePath.value = path
      window.dispatchEvent(new Event('ca-focus-editor'))
      return
    }
    if (!workspaceId.value) return
    try {
      const data = await api<{ path: string; content: string }>(
        `/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(path)}`,
      )
      openFiles.value = [...openFiles.value, { path: data.path, content: data.content, dirty: false }]
      activePath.value = data.path
    } catch {
      if (review) {
        openFiles.value = [...openFiles.value, { path, content: review.after, dirty: false }]
        activePath.value = path
      } else {
        return
      }
    }
    window.dispatchEvent(new Event('ca-focus-editor'))
  }

  async function openAgentFile(path: string) {
    if (!path) return
    activity.value = 'files'
    await revealInTree(path)
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

  function updateOpenContent(path: string, content: string) {
    const file = openFiles.value.find((f) => f.path === path)
    if (!file || file.content === content) return
    file.content = content
    file.dirty = true
  }

  async function saveOpenFile() {
    const file = openFile.value
    if (!workspaceId.value || !file) return
    await api(`/api/workspaces/${workspaceId.value}/file?path=${encodeURIComponent(file.path)}`, {
      method: 'PUT',
      body: JSON.stringify({ content: file.content }),
    })
    file.dirty = false
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

  async function openConversation(id: string) {
    stopStream?.()
    conversationId.value = id
    const data = await api<Conversation & { messages: ChatMessage[]; active_run: any }>(`/api/conversations/${id}`)
    messages.value = data.messages || []
    mode.value = (data.mode as typeof mode.value) || 'agent'
    modelId.value = data.model_id
    applied.value = new Set()
    if (data.active_run) {
      lastEventId.value = data.active_run.last_event_id
      runStatus.value = data.active_run.status
      if (['queued', 'running'].includes(data.active_run.status)) {
        attachRun(data.active_run.id, data.active_run.last_event_id)
      }
    } else {
      runStatus.value = 'idle'
      lastEventId.value = null
    }
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

  function onEvent(event: StreamEnvelope) {
    if (applied.value.has(event.event_id)) return
    applied.value.add(event.event_id)
    lastEventId.value = event.event_id
    messages.value = applyEvent(messages.value, event)
    const type = String(event.payload?.block_type || '')
    if (
      (event.type === 'block.started' || event.type === 'block.completed') &&
      (type === 'file.diff' || type === 'file.delete')
    ) {
      upsertReview({
        id: String(event.payload?.block_id || ''),
        type,
        meta: (event.payload?.meta as Record<string, unknown>) || {},
      })
      const meta = (event.payload?.meta as Record<string, unknown>) || {}
      const changedPath = String(meta.path || '')
      if (changedPath && typeof meta.after === 'string') {
        const file = openFiles.value.find((f) => f.path === changedPath)
        if (file && !file.dirty) {
          file.content = meta.after
          window.dispatchEvent(new CustomEvent('ca-file-reload', { detail: { path: changedPath, content: meta.after } }))
        }
      }
    }
    if (event.type === 'run.started') runStatus.value = 'running'
    if (event.type === 'run.completed' || event.type === 'run.failed' || event.type === 'run.cancelled') {
      runStatus.value = event.type.replace('run.', '')
      refreshTree()
    }
    if (event.type === 'block.started' || event.type === 'block.completed') {
      const type = String(event.payload?.block_type || '')
      const name = String((event.payload?.meta as { name?: string } | undefined)?.name || '')
      const path = eventPath(event)
      const fileOp =
        type.startsWith('file.') ||
        ['write_file', 'search_replace', 'delete_file'].includes(name)
      if (fileOp) scheduleTreeRefresh(path || undefined)
    }
  }

  function attachRun(runId: string, after?: string | null) {
    stopStream?.()
    activeRunId.value = runId
    runStatus.value = 'running'
    stopStream = subscribeRun(runId, after || null, onEvent, () => {
      runStatus.value = runStatus.value === 'running' ? 'completed' : runStatus.value
      if (activeRunId.value === runId) activeRunId.value = null
      loadConversations()
    })
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
    confirmDialog.value = { danger: true, confirmLabel: '确认', cancelLabel: '取消', ...req }
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

  async function send(text: string, references: { type: string; path: string }[] = []) {
    if (!conversationId.value) await newChat()
    if (!conversationId.value) return
    messages.value = [
      ...messages.value,
      {
        id: `local-${Date.now()}`,
        role: 'user',
        blocks: [{ id: 'u', type: 'user.text', text, meta: { references }, status: 'ok' }],
      },
    ]
    const data = await api<{ run_id: string }>(`/api/conversations/${conversationId.value}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        text,
        mode: mode.value,
        model_id: modelId.value,
        thinking: thinking.value,
        references,
      }),
    })
    lastEventId.value = null
    attachRun(data.run_id, null)
  }

  async function stop() {
    const conv = conversations.value.find((c) => c.id === conversationId.value)
    const runId = conv?.active_run_id
    if (!runId) return
    await api(`/api/runs/${runId}/cancel`, { method: 'POST' })
  }

  async function loadProviders() {
    providers.value = await api('/api/llm/providers')
    const models = providers.value.flatMap((p) => p.models || [])
    const def = models.find((m: any) => m.is_default) || models[0]
    if (def && !modelId.value) modelId.value = def.id
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

  return {
    workspaces,
    workspaceId,
    workspace,
    conversations,
    conversationId,
    messages,
    runStatus,
    mode,
    modelId,
    thinking,
    fileTree,
    childrenMap,
    expanded,
    treePath,
    openFiles,
    activePath,
    openFile,
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
    settings,
    activity,
    loadWorkspaces,
    addWorkspace,
    clearWorkspace,
    selectWorkspace,
    loadTree,
    refreshTree,
    revealInTree,
    toggleDir,
    isExpanded,
    childrenOf,
    parentPath,
    joinPath,
    createEntry,
    renameEntry,
    deleteEntry,
    openPath,
    openAgentFile,
    acceptReview,
    rejectReview,
    activateFile,
    closeFile,
    updateOpenContent,
    saveOpenFile,
    loadConversations,
    newChat,
    openConversation,
    send,
    stop,
    loadProviders,
    loadSkills,
    loadSettings,
    saveSettings,
  }
})
