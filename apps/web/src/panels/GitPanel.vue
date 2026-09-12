<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import { gitMarkKind, gitMarkLabel } from '@/utils/gitStatus'
import { t, currentLocale } from '@/i18n'
import { useToast } from '@/composables/useToast'
import { useGitDiffTarget } from '@/composables/useGitDiffTarget'
import type { GitDiffTarget } from '@/utils/gitPrefs'
import AppIcon from '@/components/AppIcon.vue'
import ContextMenu, { type ContextMenuItem } from '@/components/ContextMenu.vue'
import GitGraphRow from '@/panels/GitGraphRow.vue'
import GitCommitDetail from '@/panels/GitCommitDetail.vue'
import GitCommitTreeNode from '@/panels/GitCommitTreeNode.vue'
import GitDiffView from '@/panels/GitDiffView.vue'
import GitHoverActions from '@/components/GitHoverActions.vue'
import { formatCommitTime, layoutGitGraph, type GitCommit } from '@/utils/gitGraph'
import { buildGitFileTree, collectGitDirPaths } from '@/utils/gitFileTree'

type GitFile = { path: string; code: string; staged: boolean; unstaged: boolean; conflict?: boolean }
type GitStatus = {
  ok: boolean
  error?: string
  branch: string
  ahead: number
  behind: number
  files: GitFile[]
  merging?: boolean
  rebasing?: boolean
  cherry_picking?: boolean
  conflicts?: number
}
type GitLog = { ok: boolean; error?: string; head: string; commits: GitCommit[] }
type GitBranch = { name: string; current: boolean; short: string; subject: string }
type GitStash = { ref: string; message: string }

const store = useAppStore()
const toast = useToast()
const { diffTarget, setDiffTarget } = useGitDiffTarget()
const status = ref<GitStatus | null>(null)
const log = ref<GitLog | null>(null)
const message = ref('')
const error = ref('')
const busy = ref(false)
const selected = ref<Set<string>>(new Set())
const tab = ref<'changes' | 'history'>('changes')
const selectedCommit = ref<GitCommit | null>(null)
const activePath = ref('')
const showPanelDiff = ref(false)
const changePatch = ref('')
const changeDiffError = ref('')
const loadingDiff = ref(false)
const viewMode = ref<'list' | 'tree'>((localStorage.getItem('ca.git.changes.view') as 'list' | 'tree') || 'list')
const diffLayout = ref<'down' | 'right'>((localStorage.getItem('ca.git.changes.layout') as 'down' | 'right') || 'down')
const treeExpanded = ref<Set<string>>(new Set())
const collapsedDirs = ref<Set<string>>(new Set())
const gitMenu = ref<{ x: number; y: number; path: string; kind: 'file' | 'dir' } | null>(null)
const branches = ref<GitBranch[]>([])
const stashes = ref<GitStash[]>([])
const branchOpen = ref(false)
const branchQuery = ref('')
const prOpen = ref(false)
const prBusy = ref(false)
const prTitle = ref('')
const prBody = ref('')
const prBase = ref('main')
const prError = ref('')
const generating = ref(false)

const files = computed(() => status.value?.files || [])
const notRepo = computed(() => Boolean(status.value) && !status.value?.ok)
const noCommits = computed(() => Boolean(status.value?.ok) && Boolean(log.value?.ok) && !(log.value?.commits || []).length)
const conflictFiles = computed(() => files.value.filter((f) => f.conflict || gitMarkKind(f.code) === 'conflict'))
const canCommit = computed(() => Boolean(message.value.trim()) && !busy.value && files.value.some((f) => f.staged || selected.value.has(f.path)))
const commitCmd = computed(() => {
  const needsAdd = !files.value.some((f) => f.staged) && selected.value.size > 0
  return needsAdd ? 'git add -- <paths> && git commit -m "…"' : 'git commit -m "…"'
})
const generateTargets = computed(() => {
  if (selected.value.size) return files.value.filter((f) => selected.value.has(f.path))
  const staged = files.value.filter((f) => f.staged)
  return staged.length ? staged : files.value
})
const canGenerate = computed(
  () => Boolean(status.value?.ok) && generateTargets.value.length > 0 && !busy.value && !generating.value,
)
const filteredBranches = computed(() => {
  const q = branchQuery.value.trim().toLowerCase()
  if (!q) return branches.value
  return branches.value.filter((b) => b.name.toLowerCase().includes(q))
})
const canCreateBranch = computed(() => {
  const name = branchQuery.value.trim()
  return Boolean(name) && !branches.value.some((b) => b.name === name)
})
const graphRows = computed(() => layoutGitGraph(log.value?.commits || []))
const treeRoots = computed(() => buildGitFileTree(files.value.map((file) => ({
  path: file.path,
  status: file.code,
  additions: 0,
  deletions: 0,
}))))
const activeChange = computed(() => files.value.find((file) => file.path === activePath.value) || null)
const allSelected = computed(() => files.value.length > 0 && files.value.every((file) => selected.value.has(file.path)))
const someSelected = computed(() => selected.value.size > 0 && !allSelected.value)
const stagedOnlyPaths = computed(
  () => new Set(files.value.filter((file) => file.staged && !file.unstaged).map((file) => file.path)),
)
const deletedPaths = computed(
  () => new Set(files.value.filter((file) => file.code.includes('D')).map((file) => file.path)),
)

watch(viewMode, (mode) => {
  localStorage.setItem('ca.git.changes.view', mode)
  if (mode === 'tree') expandAllDirs()
})
watch(diffLayout, (mode) => {
  localStorage.setItem('ca.git.changes.layout', mode)
})
watch(treeRoots, syncTreeDirs)

function expandAllDirs() {
  collapsedDirs.value = new Set()
  treeExpanded.value = new Set(collectGitDirPaths(treeRoots.value))
}

function syncTreeDirs() {
  if (viewMode.value !== 'tree') return
  const dirs = collectGitDirPaths(treeRoots.value)
  const alive = new Set(dirs)
  const collapsed = new Set([...collapsedDirs.value].filter((path) => alive.has(path)))
  const next = new Set<string>()
  for (const path of dirs) {
    if (!collapsed.has(path)) next.add(path)
  }
  const sameExpanded =
    next.size === treeExpanded.value.size && [...next].every((path) => treeExpanded.value.has(path))
  const sameCollapsed =
    collapsed.size === collapsedDirs.value.size && [...collapsed].every((path) => collapsedDirs.value.has(path))
  if (!sameExpanded) treeExpanded.value = next
  if (!sameCollapsed) collapsedDirs.value = collapsed
}

function toggleTreeDir(path: string) {
  const expanded = new Set(treeExpanded.value)
  const collapsed = new Set(collapsedDirs.value)
  if (expanded.has(path)) {
    expanded.delete(path)
    collapsed.add(path)
  } else {
    expanded.add(path)
    collapsed.delete(path)
  }
  treeExpanded.value = expanded
  collapsedDirs.value = collapsed
}

let pollTimer = 0
let debounceTimer = 0
let inflight = false
let queued = false

function statusKey(data: GitStatus | null) {
  if (!data) return ''
  const files = (data.files || [])
    .map((file) => `${file.path}\0${file.code}\0${Number(file.staged)}\0${Number(file.unstaged)}`)
    .join('\n')
  return `${Number(data.ok)}\0${data.branch}\0${data.ahead}\0${data.behind}\0${Number(data.merging)}\0${data.conflicts || 0}\0${data.error || ''}\n${files}`
}

function logKey(data: GitLog | null) {
  if (!data) return ''
  const commits = (data.commits || []).map((row) => `${row.hash}\0${row.subject}\0${(row.refs || []).join(',')}`).join('\n')
  return `${Number(data.ok)}\0${data.head}\0${data.error || ''}\n${commits}`
}

function fileSig(file: GitFile | undefined) {
  if (!file) return ''
  return `${file.path}\0${file.code}\0${Number(file.staged)}\0${Number(file.unstaged)}`
}

async function refreshStatus() {
  if (!store.workspaceId) return
  const prevActive = files.value.find((file) => file.path === activePath.value)
  const data = await api<GitStatus>(`/api/workspaces/${store.workspaceId}/git/status`)
  if (statusKey(data) === statusKey(status.value)) return
  status.value = data
  const valid = new Set((data.files || []).map((file) => file.path))
  selected.value = new Set([...selected.value].filter((path) => valid.has(path)))
  const nextActive = (data.files || []).find((file) => file.path === activePath.value)
  if (activePath.value && !nextActive) {
    activePath.value = ''
    showPanelDiff.value = false
    changePatch.value = ''
  } else if (showPanelDiff.value && activePath.value && fileSig(prevActive) !== fileSig(nextActive)) {
    void loadChangeDiff(activePath.value, true)
  }
  if (data && !data.ok) error.value = notRepoError(data.error)
  else error.value = ''
}

function notRepoError(raw?: string) {
  const text = (raw || '').toLowerCase()
  if (!text || text.includes('not a git')) return ''
  return raw || t('git.notRepo')
}

async function refreshLog() {
  if (!store.workspaceId) return
  const data = await api<GitLog>(`/api/workspaces/${store.workspaceId}/git/log?limit=80`)
  if (logKey(data) === logKey(log.value)) return
  log.value = data
}

async function refresh(all = false) {
  if (!store.workspaceId) return
  if (inflight) {
    queued = true
    return
  }
  inflight = true
  try {
    do {
      queued = false
      await refreshStatus()
      await loadStashes()
      if (all || tab.value === 'history') await refreshLog()
    } while (queued)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    inflight = false
  }
}

function scheduleRefresh() {
  window.clearTimeout(debounceTimer)
  debounceTimer = window.setTimeout(() => {
    void refresh()
  }, 280)
}

function onVisibility() {
  if (document.hidden || busy.value) return
  void refresh()
}

function applyCommitDraft(text: string) {
  if (!text.trim()) return
  message.value = text
  tab.value = 'changes'
}

function onCommitDraft(e: Event) {
  const detail = (e as CustomEvent<{ message?: string }>).detail
  if (detail?.message) applyCommitDraft(detail.message)
}

async function loadBranches() {
  if (!store.workspaceId) return
  try {
    const data = await api<{ branches: GitBranch[] }>(`/api/workspaces/${store.workspaceId}/git/branches`)
    branches.value = data.branches || []
  } catch {
    branches.value = []
  }
}

async function loadStashes() {
  if (!store.workspaceId) return
  try {
    const data = await api<{ stashes: GitStash[] }>(`/api/workspaces/${store.workspaceId}/git/stash`)
    stashes.value = data.stashes || []
  } catch {
    stashes.value = []
  }
}

onMounted(() => {
  window.addEventListener('ca-git-commit-draft', onCommitDraft as EventListener)
  if (store.gitCommitDraft) applyCommitDraft(store.gitCommitDraft)
  void refresh(true)
  pollTimer = window.setInterval(() => {
    if (document.hidden || busy.value) return
    void refresh()
  }, 4000)
  document.addEventListener('visibilitychange', onVisibility)
})
function onDocClick() {
  branchOpen.value = false
}

onUnmounted(() => {
  window.removeEventListener('ca-git-commit-draft', onCommitDraft as EventListener)
  window.clearInterval(pollTimer)
  window.clearTimeout(debounceTimer)
  document.removeEventListener('visibilitychange', onVisibility)
  document.removeEventListener('click', onDocClick)
})

watch(
  () => store.gitCommitDraft,
  (text) => {
    if (text) applyCommitDraft(text)
  },
)
watch(branchOpen, (open) => {
  if (open) requestAnimationFrame(() => document.addEventListener('click', onDocClick))
  else document.removeEventListener('click', onDocClick)
})
watch(() => store.workspaceId, () => {
  status.value = null
  log.value = null
  selectedCommit.value = null
  activePath.value = ''
  showPanelDiff.value = false
  changePatch.value = ''
  message.value = ''
  branchOpen.value = false
  prOpen.value = false
  void refresh(true)
})
watch(() => store.gitChangedPaths, scheduleRefresh)
watch(tab, (next) => {
  if (next === 'history') void refreshLog()
  else selectedCommit.value = null
})

function toggle(path: string, kind: 'file' | 'dir' = 'file') {
  const targets = kind === 'dir' ? filesUnder(path, 'dir') : [path]
  if (!targets.length) return
  const next = new Set(selected.value)
  const allOn = targets.every((item) => next.has(item))
  if (allOn) targets.forEach((item) => next.delete(item))
  else targets.forEach((item) => next.add(item))
  selected.value = next
}

function toggleSelectAll() {
  if (allSelected.value) selected.value = new Set()
  else selected.value = new Set(files.value.map((file) => file.path))
}

async function loadChangeDiff(path: string, quiet = false) {
  if (!store.workspaceId || !path) return
  const file = files.value.find((item) => item.path === path)
  if (!quiet) {
    loadingDiff.value = true
    changeDiffError.value = ''
  }
  try {
    const staged = Boolean(file?.staged && !file.unstaged)
    const data = await api<{ diff: string }>(
      `/api/workspaces/${store.workspaceId}/git/diff?path=${encodeURIComponent(path)}&staged=${staged ? 'true' : 'false'}`,
    )
    if (activePath.value === path) {
      const patch = data.diff || ''
      if (changePatch.value !== patch) changePatch.value = patch
      changeDiffError.value = ''
    }
  } catch (err) {
    if (activePath.value === path) {
      if (!quiet) changePatch.value = ''
      changeDiffError.value = err instanceof Error ? err.message : String(err)
    }
  } finally {
    if (!quiet) loadingDiff.value = false
  }
}

function showChange(path: string, force?: GitDiffTarget) {
  activePath.value = path
  const mode = force || diffTarget.value
  if (mode === 'editor') {
    showPanelDiff.value = false
    changePatch.value = ''
    changeDiffError.value = ''
    void openDiffInEditor(path)
    return
  }
  showPanelDiff.value = true
  void loadChangeDiff(path)
}

function closeDiff() {
  showPanelDiff.value = false
  activePath.value = ''
  changePatch.value = ''
  changeDiffError.value = ''
}

function setDiffLayout(mode: 'down' | 'right') {
  diffLayout.value = mode
}

function chooseDiffTarget(mode: GitDiffTarget) {
  const same = diffTarget.value === mode
  setDiffTarget(mode)
  if (mode === 'editor') {
    showPanelDiff.value = false
    if (activePath.value) void openDiffInEditor(activePath.value)
    return
  }
  if (activePath.value) {
    showPanelDiff.value = true
    if (!same || !changePatch.value) void loadChangeDiff(activePath.value)
  }
}

async function openDiffInEditor(path?: string) {
  const target = path || activePath.value
  if (!target) return
  await store.openWorkingDiff(target)
}

function filesUnder(path: string, kind: 'file' | 'dir') {
  if (kind === 'file') return [path]
  const prefix = path.replace(/\/$/, '') + '/'
  return files.value.filter((file) => file.path === path || file.path.startsWith(prefix)).map((file) => file.path)
}

function firstFileUnder(path: string, kind: 'file' | 'dir') {
  if (kind === 'file') return path
  return filesUnder(path, kind)[0] || ''
}

function onContext(e: MouseEvent, path: string, kind: 'file' | 'dir') {
  e.preventDefault()
  e.stopPropagation()
  gitMenu.value = { x: e.clientX, y: e.clientY, path, kind }
}

const ctxItems = computed((): ContextMenuItem[] => {
  const item = gitMenu.value
  if (!item) return []
  const kids = filesUnder(item.path, item.kind)
  const file = files.value.find((entry) => entry.path === item.path)
  const untracked = item.kind === 'dir'
    ? Boolean(kids.length) && kids.every((p) => files.value.find((entry) => entry.path === p)?.code === '?')
    : file?.code === '?'
  const deleted = file?.code.includes('D')
  const noHead = item.kind === 'dir' || untracked || file?.code.includes('A')
  return [
    { id: 'open-changes', label: t('git.openChanges'), icon: 'git', disabled: item.kind === 'dir' && !kids.length },
    { id: 'open-editor-diff', label: t('git.openInEditor'), icon: 'file', disabled: item.kind === 'dir' && !kids.length },
    { id: 'open-file', label: t('git.openFile'), icon: 'file', disabled: item.kind === 'dir' || deleted },
    { id: 'open-head', label: '打开文件 (HEAD)', icon: 'file', disabled: noHead },
    { id: 'sep-1', separator: true },
    { id: 'discard', label: '放弃更改', icon: 'trash', danger: true },
    { id: 'stage', label: '暂存更改', icon: 'check' },
    { id: 'ignore', label: '添加到 .gitignore', icon: 'close' },
    { id: 'sep-2', separator: true },
    { id: 'reveal', label: '在资源管理器中显示', icon: 'folder' },
  ]
})

async function onCtxSelect(id: string) {
  const item = gitMenu.value
  if (!item) return
  await runFileAction(id, item.path, item.kind)
}

async function runFileAction(id: string, path: string, kind: 'file' | 'dir' = 'file') {
  if (!store.workspaceId || !path) return
  try {
    error.value = ''
    if (id === 'open-changes') {
      const target = firstFileUnder(path, kind)
      if (target) showChange(target, 'panel')
      return
    }
    if (id === 'open-editor-diff') {
      const target = firstFileUnder(path, kind)
      if (target) showChange(target, 'editor')
      return
    }
    if (id === 'open-file') {
      if (kind === 'dir') return
      openFile(path)
      return
    }
    if (id === 'open-head') {
      await store.openRevisionFile(path, 'HEAD')
      return
    }
    if (id === 'stage') {
      status.value = await api(`/api/workspaces/${store.workspaceId}/git/stage`, {
        method: 'POST',
        body: JSON.stringify({ paths: [path] }),
      })
      void store.loadGitChangedPaths()
      return
    }
    if (id === 'unstage') {
      status.value = await api(`/api/workspaces/${store.workspaceId}/git/unstage`, {
        method: 'POST',
        body: JSON.stringify({ paths: [path] }),
      })
      void store.loadGitChangedPaths()
      return
    }
    if (id === 'discard') {
      const ok = await store.askConfirm({
        title: t('git.discard'),
        summary: kind === 'dir' ? t('git.discardDir', { path }) : t('git.discardFile', { path }),
        confirmLabel: t('git.discardAction'),
        danger: true,
      })
      if (!ok) return
      status.value = await api(`/api/workspaces/${store.workspaceId}/git/discard`, {
        method: 'POST',
        body: JSON.stringify({ paths: [path] }),
      })
      void store.refreshTree()
      const prefix = path.replace(/\/$/, '') + '/'
      if (activePath.value === path || activePath.value.startsWith(prefix)) {
        closeDiff()
      }
      return
    }
    if (id === 'ignore') {
      status.value = await api(`/api/workspaces/${store.workspaceId}/git/ignore`, {
        method: 'POST',
        body: JSON.stringify({ paths: [path] }),
      })
      void store.refreshTree()
      return
    }
    if (id === 'reveal') {
      store.openExplorerPanel()
      await store.revealInTree(path)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

function mark(code: string) {
  return gitMarkLabel(code)
}

function actionTip(hint: string, cmd: string) {
  return `${hint}\n${cmd}`
}
function gitErrorText(err: unknown) {
  const raw = err instanceof Error ? err.message : String(err)
  try {
    const parsed = JSON.parse(raw) as { message?: unknown }
    if (parsed && typeof parsed === 'object' && parsed.message) return String(parsed.message)
  } catch {
    /* keep raw */
  }
  return raw
}

async function run(label: string, fn: () => Promise<void>, danger = true) {
  const ok = await store.askConfirm({
    title: t('git.confirmTitle'),
    summary: label,
    confirmLabel: t('common.continue'),
    danger,
  })
  if (!ok) return false
  busy.value = true
  error.value = ''
  try {
    await fn()
    await refresh(true)
    return true
  } catch (err) {
    error.value = gitErrorText(err)
    if (/overwritten|local changes|uncommitted|would be overwritten|未提交/i.test(error.value)) {
      error.value = `${error.value}\n${t('git.stashHint')}`
    }
    return false
  } finally {
    busy.value = false
  }
}

async function generateCommitMessage() {
  if (!canGenerate.value || !store.workspaceId) return
  generating.value = true
  error.value = ''
  try {
    const data = await api<{ message: string }>(`/api/workspaces/${store.workspaceId}/git/commit-message`, {
      method: 'POST',
      body: JSON.stringify({
        paths: generateTargets.value.map((f) => f.path),
        model_id: store.modelId || undefined,
        locale: currentLocale(),
        hint: message.value.trim(),
      }),
    })
    const next = (data.message || '').trim()
    if (!next) {
      toast.info(t('git.generateEmpty'))
      return
    }
    message.value = next
    store.gitCommitDraft = next
    tab.value = 'changes'
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err)
    if (raw.includes('llm.no_model')) {
      toast.warning(t('chat.needModel'))
      window.dispatchEvent(new Event('ca-open-models'))
      return
    }
    error.value = gitErrorText(err)
  } finally {
    generating.value = false
  }
}

async function stageSelected() {
  const paths = [...selected.value]
  if (!paths.length) return
  status.value = await api(`/api/workspaces/${store.workspaceId}/git/stage`, {
    method: 'POST',
    body: JSON.stringify({ paths }),
  })
  selected.value = new Set()
  void store.loadGitChangedPaths()
}

async function commit() {
  const msg = message.value.trim()
  if (!msg) return
  const paths = files.value.some((f) => f.staged) ? [] : [...selected.value]
  await run(t('git.commitRun', { msg }), async () => {
    status.value = await api(`/api/workspaces/${store.workspaceId}/git/commit`, {
      method: 'POST',
      body: JSON.stringify({ message: msg, paths }),
    })
    message.value = ''
    store.gitCommitDraft = ''
    selected.value = new Set()
    void store.loadGitChangedPaths()
  })
}

async function push() {
  const branch = status.value?.branch || 'HEAD'
  await run(t('git.pushRun', { branch }), async () => {
    status.value = await api(`/api/workspaces/${store.workspaceId}/git/push`, {
      method: 'POST',
      body: JSON.stringify({ remote: 'origin' }),
    })
  })
}

async function pull() {
  const branch = status.value?.branch || ''
  await run(t('git.pullRun', { branch: branch || 'HEAD' }), async () => {
    status.value = await api(`/api/workspaces/${store.workspaceId}/git/pull`, {
      method: 'POST',
      body: JSON.stringify({ remote: 'origin' }),
    })
  }, false)
}

async function initRepo() {
  await run(t('git.initRun'), async () => {
    status.value = await api(`/api/workspaces/${store.workspaceId}/git/init`, { method: 'POST' })
    void store.loadGitChangedPaths()
    toast.success(t('git.initDone'))
  }, false)
}

async function toggleBranchMenu() {
  branchOpen.value = !branchOpen.value
  if (branchOpen.value) {
    branchQuery.value = ''
    await loadBranches()
  }
}

async function checkoutBranch(name: string, create = false) {
  branchOpen.value = false
  await run(create ? t('git.branchCreateRun', { name }) : t('git.branchSwitchRun', { name }), async () => {
    status.value = await api(`/api/workspaces/${store.workspaceId}/git/checkout`, {
      method: 'POST',
      body: JSON.stringify({ name, create }),
    })
    void store.loadGitChangedPaths()
  }, Boolean(files.value.length))
}

function onBranchEnter() {
  const name = branchQuery.value.trim()
  if (!name) return
  const existing = branches.value.find((b) => b.name === name)
  void checkoutBranch(name, !existing)
}

async function stashPush() {
  await run(t('git.stashPushRun'), async () => {
    const data = await api<GitStatus & { stashes?: GitStash[] }>(`/api/workspaces/${store.workspaceId}/git/stash`, {
      method: 'POST',
      body: JSON.stringify({ action: 'push', include_untracked: true }),
    })
    status.value = data
    if (data.stashes) stashes.value = data.stashes
    void store.loadGitChangedPaths()
  }, false)
}

async function stashPop() {
  await run(t('git.stashPopRun'), async () => {
    const data = await api<GitStatus & { stashes?: GitStash[] }>(`/api/workspaces/${store.workspaceId}/git/stash`, {
      method: 'POST',
      body: JSON.stringify({ action: 'pop' }),
    })
    status.value = data
    if (data.stashes) stashes.value = data.stashes
    void store.loadGitChangedPaths()
  })
}

async function takeConflict(side: 'ours' | 'theirs') {
  const path = activeChange.value?.path
  if (!path) return
  await run(side === 'ours' ? t('git.takeOursRun', { path }) : t('git.takeTheirsRun', { path }), async () => {
    status.value = await api(`/api/workspaces/${store.workspaceId}/git/conflict`, {
      method: 'POST',
      body: JSON.stringify({ path, side }),
    })
    void store.loadGitChangedPaths()
    void loadChangeDiff(path, true)
  })
}

async function continueMerge() {
  await run(t('git.mergeContinueRun'), async () => {
    status.value = await api(`/api/workspaces/${store.workspaceId}/git/merge/continue`, { method: 'POST' })
  })
}

function openConflictFiles() {
  for (const file of conflictFiles.value) void store.openAgentFile(file.path)
}

async function openPrDialog() {
  prError.value = ''
  prOpen.value = true
  prBusy.value = true
  try {
    const draft = await api<{ title: string; body: string; base: string; head: string }>(
      `/api/workspaces/${store.workspaceId}/git/pr-draft`,
    )
    prTitle.value = draft.title || ''
    prBody.value = draft.body || ''
    prBase.value = draft.base || 'main'
  } catch (err) {
    prError.value = err instanceof Error ? err.message : String(err)
  } finally {
    prBusy.value = false
  }
}

async function submitPr() {
  const title = prTitle.value.trim()
  if (!title || !store.workspaceId) return
  prBusy.value = true
  prError.value = ''
  try {
    const result = await api<{ ok: boolean; url?: string; compare_url?: string; method?: string; error?: string }>(
      `/api/workspaces/${store.workspaceId}/git/pull-request`,
      {
        method: 'POST',
        body: JSON.stringify({
          title,
          body: prBody.value,
          base: prBase.value,
          push: true,
        }),
      },
    )
    const url = result.url || result.compare_url
    if (url) window.open(url, '_blank', 'noopener')
    if (result.ok) {
      toast.success(result.method === 'url' ? t('git.prOpenedCompare') : t('git.prCreated'))
      prOpen.value = false
      await refresh(true)
    } else if (url) {
      toast.info(t('git.prOpenedCompare'))
      prOpen.value = false
    } else {
      prError.value = result.error || t('git.prFailed')
    }
  } catch (err) {
    prError.value = err instanceof Error ? err.message : String(err)
  } finally {
    prBusy.value = false
  }
}

function openFile(path: string) {
  store.openAgentFile(path)
}

function openCommit(row: GitCommit) {
  selectedCommit.value = row
}
</script>

<template>
  <div class="panel-shell git panel-chromeless">
    <div class="git-bar">
      <div class="branch-wrap">
        <button type="button" class="branch" :disabled="!status?.ok || busy" @click.stop="toggleBranchMenu">
          <AppIcon name="git" :size="16" :stroke-width="1.75" />
          <span>{{ status?.branch || 'Git' }}</span>
          <AppIcon name="chevron-down" :size="12" />
        </button>
        <div v-if="branchOpen" class="branch-menu" @click.stop @mousedown.stop>
          <input
            v-model="branchQuery"
            class="branch-input"
            :placeholder="t('git.branchPlaceholder')"
            @keydown.enter.prevent="onBranchEnter"
          />
          <button
            v-if="canCreateBranch"
            type="button"
            class="branch-item create"
            @click="checkoutBranch(branchQuery.trim(), true)"
          >
            {{ t('git.branchCreate', { name: branchQuery.trim() }) }}
          </button>
          <button
            v-for="item in filteredBranches"
            :key="item.name"
            type="button"
            class="branch-item"
            :class="{ current: item.current }"
            @click="checkoutBranch(item.name)"
          >
            <span>{{ item.name }}</span>
            <small>{{ item.subject }}</small>
          </button>
        </div>
      </div>
      <span v-if="status?.ahead" class="pill">↑{{ status.ahead }}</span>
      <button
        v-if="status?.behind"
        type="button"
        class="pill pill-btn"
        :disabled="busy"
        :title="t('git.pull')"
        @click="pull"
      >
        ↓{{ status.behind }}
      </button>
      <button type="button" class="git-text-btn" :disabled="busy || !status?.ok" :title="t('git.pull')" @click="pull">
        {{ t('git.pull') }}
      </button>
      <button
        v-if="stashes.length"
        type="button"
        class="pill pill-btn"
        :disabled="busy"
        :title="t('git.stashPop')"
        @click="stashPop"
      >
        stash {{ stashes.length }}
      </button>
      <span class="spacer" />
      <div class="seg" role="tablist" :aria-label="t('git.view')">
        <button
          type="button"
          role="tab"
          :aria-selected="tab === 'changes'"
          :class="{ on: tab === 'changes' }"
          @click="tab = 'changes'"
        >
          {{ t('git.changes') }}
          <span v-if="files.length" class="seg-count">{{ files.length }}</span>
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="tab === 'history'"
          :class="{ on: tab === 'history' }"
          @click="tab = 'history'"
        >
          {{ t('git.history') }}
        </button>
      </div>
      <template v-if="tab === 'changes'">
        <button
          type="button"
          class="ghost-icon-btn"
          :class="{ active: viewMode === 'list' }"
          :title="t('git.list')"
          @click="viewMode = 'list'"
        >
          <AppIcon name="list" :size="16" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ghost-icon-btn"
          :class="{ active: viewMode === 'tree' }"
          :title="t('git.tree')"
          @click="viewMode = 'tree'"
        >
          <AppIcon name="tree" :size="16" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ghost-icon-btn"
          :class="{ active: diffTarget === 'panel' }"
          :title="t('git.diffTargetPanelTip')"
          @click="chooseDiffTarget('panel')"
        >
          <AppIcon name="git" :size="16" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ghost-icon-btn"
          :class="{ active: diffTarget === 'editor' }"
          :title="t('git.diffTargetEditorTip')"
          @click="chooseDiffTarget('editor')"
        >
          <AppIcon name="file" :size="16" :stroke-width="1.75" />
        </button>
      </template>
      <button type="button" class="ghost-icon-btn" :title="t('common.refresh')" @click="refresh(true)">
        <AppIcon name="refresh" :size="16" :stroke-width="1.75" />
      </button>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
    <div v-if="notRepo" class="git-setup">
      <h3>{{ t('git.notRepo') }}</h3>
      <p class="setup-lead">{{ t('git.initLead') }}</p>
      <span class="act-wrap" :title="actionTip(t('git.initRepo'), 'git init -b main')">
        <button
          type="button"
          class="btn btn-sm btn-primary"
          :disabled="busy || !store.workspaceId"
          @click="initRepo"
        >
          {{ t('git.initRepo') }}
        </button>
      </span>
      <p class="setup-next">{{ t('git.initNext') }}</p>
      <ol class="setup-steps">
        <li>
          <span>{{ t('git.initStep1') }}</span>
          <code>git add -- &lt;paths&gt;</code>
        </li>
        <li>
          <span>{{ t('git.initStep2') }}</span>
          <code>git commit -m "Initial commit"</code>
        </li>
        <li>
          <span>{{ t('git.initStep3') }}</span>
          <code>git remote add origin &lt;url&gt; && git push -u origin HEAD</code>
        </li>
      </ol>
    </div>
    <div v-else-if="tab === 'changes' && (conflictFiles.length || status?.merging || status?.rebasing)" class="conflict-banner">
      <p>
        <template v-if="conflictFiles.length">{{ t('git.conflictGuide', { n: conflictFiles.length }) }}</template>
        <template v-else-if="status?.merging">{{ t('git.mergeReady') }}</template>
        <template v-else>{{ t('git.rebaseHint') }}</template>
      </p>
      <div class="conflict-actions">
        <button v-if="conflictFiles.length" type="button" class="btn" @click="openConflictFiles">{{ t('git.openConflicts') }}</button>
        <button
          v-if="status?.merging && !conflictFiles.length"
          type="button"
          class="btn btn-primary"
          :disabled="busy"
          @click="continueMerge"
        >
          {{ t('git.mergeContinue') }}
        </button>
      </div>
    </div>
    <div
      v-if="!notRepo && tab === 'changes'"
      class="changes"
      :class="{ 'has-diff': showPanelDiff && !!activeChange, 'diff-right': diffLayout === 'right', 'diff-down': diffLayout === 'down' }"
    >
      <div class="files">
        <div v-if="noCommits" class="first-commit">
          <p>{{ t('git.firstCommitHint') }}</p>
          <ol class="setup-steps compact">
            <li>
              <span>{{ t('git.initStep1') }}</span>
              <code>git add -- &lt;paths&gt;</code>
            </li>
            <li>
              <span>{{ t('git.initStep2') }}</span>
              <code>git commit -m "Initial commit"</code>
            </li>
          </ol>
        </div>
        <label v-if="files.length" class="files-head">
          <input
            type="checkbox"
            class="check"
            :checked="allSelected"
            :indeterminate="someSelected"
            :disabled="busy"
            @change="toggleSelectAll"
          />
          <span>{{ allSelected ? t('git.deselectAll') : t('git.selectAll') }}</span>
          <span class="select-count">{{ selected.size }}/{{ files.length }}</span>
        </label>
        <template v-if="viewMode === 'list'">
          <div
            v-for="file in files"
            :key="file.path"
            class="row"
            :class="{ on: activePath === file.path, conflict: file.conflict }"
            @contextmenu.prevent.stop="onContext($event, file.path, 'file')"
          >
            <input
              type="checkbox"
              class="check"
              :checked="selected.has(file.path)"
              @click.stop
              @change="toggle(file.path)"
            />
            <button
              type="button"
              class="row-main"
              :title="`${mark(file.code)} · ${file.path}`"
              @click="showChange(file.path)"
              @dblclick="openFile(file.path)"
            >
              <span class="code">{{ file.code }}</span>
              <span class="path">{{ file.path }}</span>
            </button>
            <GitHoverActions
              kind="file"
              :deleted="file.code.includes('D')"
              :staged-only="file.staged && !file.unstaged"
              :disabled="busy"
              @action="(id) => runFileAction(id, file.path, 'file')"
            />
          </div>
        </template>
        <GitCommitTreeNode
          v-else
          v-for="node in treeRoots"
          :key="node.path"
          :node="node"
          :depth="0"
          :expanded="treeExpanded"
          :active-path="activePath"
          selectable
          :selected="selected"
          :staged-only="stagedOnlyPaths"
          :deleted-paths="deletedPaths"
          :busy="busy"
          @toggle="toggleTreeDir"
          @select="showChange"
          @open="openFile"
          @check="toggle"
          @context="onContext"
          @action="runFileAction"
        />
        <p v-if="status?.ok && !files.length" class="empty">{{ t('git.clean') }}</p>
      </div>
      <div v-if="showPanelDiff && activeChange" class="diff-pane">
        <div class="diff-head">
          <span class="diff-title">{{ mark(activeChange.code) }} · {{ activeChange.path }}</span>
          <span class="diff-head-actions">
            <span v-if="activeChange.staged && !activeChange.unstaged" class="pill">{{ t('git.staged') }}</span>
            <button
              type="button"
              class="ghost-icon-btn"
              :class="{ active: diffLayout === 'down' }"
              :title="t('git.layoutDown')"
              @click="setDiffLayout('down')"
            >
              <AppIcon name="panel-bottom" :size="14" :stroke-width="1.75" />
            </button>
            <button
              type="button"
              class="ghost-icon-btn"
              :class="{ active: diffLayout === 'right' }"
              :title="t('git.layoutRight')"
              @click="setDiffLayout('right')"
            >
              <AppIcon name="panel-right" :size="14" :stroke-width="1.75" />
            </button>
            <button type="button" class="ghost-icon-btn" :title="t('git.openInEditor')" @click="openDiffInEditor()">
              <AppIcon name="file" :size="14" :stroke-width="1.75" />
            </button>
            <button type="button" class="ghost-icon-btn" :title="t('git.closeDiff')" @click="closeDiff">
              <AppIcon name="close" :size="14" :stroke-width="1.75" />
            </button>
          </span>
        </div>
        <div v-if="activeChange.conflict || gitMarkKind(activeChange.code) === 'conflict'" class="conflict-file">
          <button type="button" class="btn" :disabled="busy" @click="takeConflict('ours')">{{ t('git.takeOurs') }}</button>
          <button type="button" class="btn" :disabled="busy" @click="takeConflict('theirs')">{{ t('git.takeTheirs') }}</button>
        </div>
        <p v-if="changeDiffError" class="err">{{ changeDiffError }}</p>
        <p v-else-if="loadingDiff" class="empty">{{ t('git.loadingDiff') }}</p>
        <GitDiffView v-else :patch="changePatch" />
      </div>
    </div>
    <GitCommitDetail
      v-else-if="!notRepo && selectedCommit && store.workspaceId"
      :workspace-id="store.workspaceId"
      :rev="selectedCommit.hash"
      :preview="selectedCommit"
      @back="selectedCommit = null"
      @open-file="openFile"
    />
    <div v-else-if="!notRepo" class="history">
      <button
        v-for="row in graphRows"
        :key="row.hash"
        type="button"
        class="commit"
        :class="{ head: row.is_head }"
        :title="row.hash"
        @click="openCommit(row)"
      >
        <GitGraphRow :row="row" />
        <span class="commit-body">
          <span class="subject-row">
            <span class="subject">{{ row.subject || t('git.noSubject') }}</span>
            <span v-for="refName in row.refs" :key="refName" class="ref" :class="{ head: refName === 'HEAD' }">{{ refName }}</span>
          </span>
          <span class="meta">{{ row.author }} · {{ formatCommitTime(row.date) }} · {{ row.short }}</span>
        </span>
      </button>
      <p v-if="log?.ok && !graphRows.length" class="empty">{{ t('git.noCommits') }}</p>
    </div>
    <footer v-if="!notRepo && tab === 'changes'">
      <div class="msg-box">
        <textarea v-model="message" rows="3" :placeholder="t('git.message')" :disabled="generating" />
        <span
          class="act-wrap msg-ai-wrap"
          :title="actionTip(t('git.generateTip'), t('git.generateHint'))"
        >
          <button
            type="button"
            class="btn btn-sm msg-ai"
            :disabled="!canGenerate"
            @click="generateCommitMessage"
          >
            <AppIcon name="sparkles" :size="13" :stroke-width="1.75" />
            {{ generating ? t('git.generating') : t('git.generate') }}
          </button>
        </span>
      </div>
      <div class="actions">
        <span class="act-wrap" :title="actionTip(t('git.tipStage'), 'git add -- <paths>')">
          <button type="button" class="btn btn-sm" :disabled="!selected.size || busy" @click="stageSelected">{{ t('git.stageSelected') }}</button>
        </span>
        <span class="act-wrap" :title="actionTip(t('git.tipCommit'), commitCmd)">
          <button type="button" class="btn btn-sm btn-primary" :disabled="!canCommit" @click="commit">{{ t('git.commit') }}</button>
        </span>
        <span class="act-wrap" :title="actionTip(t('git.tipPush'), 'git push origin')">
          <button type="button" class="btn btn-sm" :disabled="busy || !status?.ok" @click="push">{{ t('git.push') }}</button>
        </span>
        <span class="act-wrap" :title="actionTip(t('git.tipStash'), 'git stash push -u')">
          <button type="button" class="btn btn-sm" :disabled="busy || !status?.ok || !files.length" @click="stashPush">{{ t('git.stash') }}</button>
        </span>
        <span class="act-wrap" :title="actionTip(t('git.tipStashPop'), 'git stash pop')">
          <button type="button" class="btn btn-sm" :disabled="busy || !stashes.length" @click="stashPop">{{ t('git.stashPop') }}</button>
        </span>
        <span class="act-wrap" :title="actionTip(t('git.tipPr'), 'git push -u origin HEAD && gh pr create')">
          <button type="button" class="btn btn-sm" :disabled="busy || !status?.ok" @click="openPrDialog">{{ t('git.openPr') }}</button>
        </span>
      </div>
    </footer>
    <div v-if="prOpen" class="pr-root" @click.self="prOpen = false">
      <div class="pr-panel" role="dialog" :aria-label="t('git.openPr')">
        <header>
          <h3>{{ t('git.openPr') }}</h3>
          <button type="button" class="ghost-icon-btn" @click="prOpen = false">
            <AppIcon name="close" :size="14" />
          </button>
        </header>
        <label>
          {{ t('git.prTitle') }}
          <input v-model="prTitle" class="field-control" :disabled="prBusy" />
        </label>
        <label>
          {{ t('git.prBase') }}
          <input v-model="prBase" class="field-control" :disabled="prBusy" />
        </label>
        <label>
          {{ t('git.prBody') }}
          <textarea v-model="prBody" rows="8" :disabled="prBusy" />
        </label>
        <p v-if="prError" class="err">{{ prError }}</p>
        <div class="actions">
          <button type="button" class="btn" :disabled="prBusy" @click="prOpen = false">{{ t('common.cancel') }}</button>
          <button type="button" class="btn btn-primary" :disabled="prBusy || !prTitle.trim()" @click="submitPr">
            {{ t('git.createPr') }}
          </button>
        </div>
      </div>
    </div>
    <ContextMenu
      v-if="gitMenu"
      :x="gitMenu.x"
      :y="gitMenu.y"
      :items="ctxItems"
      @select="onCtxSelect"
      @close="gitMenu = null"
    />
  </div>
</template>

<style scoped>
.git { overflow: visible; min-height: 0; position: relative; }
.git-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 6px 10px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--panel-bg);
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}
.git-bar .spacer { margin-left: auto; }
.branch-wrap {
  position: relative;
  min-width: 0;
  flex: 0 1 auto;
}
.branch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 180px;
  font-size: 12.5px;
  font-weight: 600;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 6px;
}
.branch:hover:not(:disabled) { background: var(--bg-muted); }
.branch:disabled { opacity: 0.55; cursor: default; }
.branch span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.branch-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 30;
  width: min(280px, 70vw);
  max-height: 280px;
  overflow: auto;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-elevated);
  box-shadow: 0 10px 28px color-mix(in srgb, #000 18%, transparent);
}
.branch-input {
  width: 100%;
  margin-bottom: 4px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg);
  color: var(--text);
  padding: 6px 8px;
  font: inherit;
  font-size: 12px;
}
.branch-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  border: 0;
  background: transparent;
  color: var(--text);
  padding: 6px 8px;
  border-radius: 7px;
  cursor: pointer;
  text-align: left;
  font: inherit;
  font-size: 12.5px;
}
.branch-item small {
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.branch-item:hover,
.branch-item.current { background: var(--bg-muted); }
.branch-item.create { color: var(--primary); font-weight: 600; }
.git-text-btn {
  height: var(--ghost-btn-height);
  padding: 0 8px;
  border: 0;
  border-radius: var(--ghost-btn-radius);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--ghost-btn-font-size);
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;
}
.git-text-btn:hover:not(:disabled) { color: var(--text-h); }
.git-text-btn:disabled { opacity: 0.45; cursor: default; }
.pill {
  font-size: 11px;
  color: var(--primary);
  background: var(--code-bg);
  border-radius: 999px;
  padding: 1px 7px;
  flex-shrink: 0;
}
.pill-btn {
  border: 0;
  cursor: pointer;
  font: inherit;
}
.pill-btn:disabled { opacity: 0.5; cursor: default; }
.conflict-banner {
  padding: 8px 12px;
  background: color-mix(in srgb, var(--danger) 10%, var(--bg));
  border-bottom: var(--border-width) solid var(--border);
  flex-shrink: 0;
}
.conflict-banner p {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--text);
  line-height: 1.45;
}
.conflict-actions,
.conflict-file {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.conflict-file {
  padding: 0 12px 8px;
  flex-shrink: 0;
}
.row.conflict .code { color: var(--danger); }
.pr-root {
  position: absolute;
  inset: 0;
  z-index: 40;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 12px;
  background: color-mix(in srgb, var(--bg) 55%, transparent);
}
.pr-panel {
  width: min(420px, 100%);
  max-height: 90%;
  overflow: auto;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pr-panel header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.pr-panel h3 {
  margin: 0;
  font-size: 14px;
}
.pr-panel label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}
.pr-panel textarea {
  margin: 0;
}
.seg {
  display: inline-flex;
  align-items: center;
  padding: 0;
  gap: 2px;
  flex-shrink: 0;
  border-radius: 0;
  background: transparent;
  border: 0;
}
.seg button {
  height: var(--ghost-btn-height);
  padding: 0 8px;
  border: 0;
  border-radius: var(--ghost-btn-radius);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--ghost-btn-font-size);
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  line-height: 1;
  transition: opacity 0.15s ease, color 0.12s ease;
}
.seg button:hover:not(.on) {
  opacity: var(--ghost-hover-opacity);
  color: var(--text-h);
}
.seg button.on {
  background: transparent;
  color: var(--primary);
  opacity: 1;
  box-shadow: none;
}
.seg-count {
  min-width: 16px;
  height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 10px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.err {
  margin: 0;
  padding: 8px 12px;
  color: var(--danger);
  font-size: 12px;
}
.files,
.history {
  flex: 1;
  overflow: auto;
  padding: 6px 0 10px;
}
.changes {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.changes .files {
  flex: 1;
  min-height: 0;
  padding: 0 0 6px;
}
.files-head {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 28px;
  padding: 0 12px;
  margin-bottom: 2px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--panel-bg);
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}
.files-head .select-count {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  font-size: 11px;
}
.changes.has-diff.diff-down .files {
  flex: 0 0 auto;
  max-height: 42%;
  border-bottom: var(--border-width) solid var(--border);
}
.changes.has-diff.diff-right {
  flex-direction: row;
}
.changes.has-diff.diff-right .files {
  flex: 0 0 36%;
  max-height: none;
  min-width: 148px;
  max-width: 52%;
  border-right: var(--border-width) solid var(--border);
  border-bottom: 0;
}
.row,
.commit {
  --git-row-bg: var(--panel-bg);
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  background: var(--git-row-bg);
  color: var(--text);
  padding: 6px 12px;
  cursor: pointer;
  text-align: left;
  font-size: 12.5px;
}
.row {
  position: relative;
}
.row-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
  font-size: inherit;
  padding: 0;
}
.check {
  width: 13px;
  height: 13px;
  margin: 0;
  flex-shrink: 0;
  accent-color: var(--primary);
}
.diff-pane {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}
.diff-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px 4px 12px;
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.diff-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.diff-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.commit {
  align-items: stretch;
  padding: 0 10px 0 6px;
  min-height: 40px;
}
.row:hover,
.commit:hover { --git-row-bg: var(--bg-muted); }
.row.on,
.commit.head { --git-row-bg: var(--primary-soft); }
.row:hover :deep(.git-hover-actions),
.row:focus-within :deep(.git-hover-actions) {
  opacity: 1;
  pointer-events: auto;
}
.code {
  font-family: var(--mono);
  min-width: 1.25em;
  color: var(--primary);
  flex-shrink: 0;
}
.path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--mono);
  text-align: left;
}
.tag { color: var(--text-muted); font-size: 11px; flex-shrink: 0; }
.commit-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  padding: 6px 0;
}
.subject-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.subject {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  font-size: 12.5px;
}
.ref {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--code-bg);
  color: var(--text-muted);
}
.ref.head {
  color: var(--primary);
  background: var(--primary-soft);
}
.meta {
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty {
  margin: 24px 12px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}
.git-setup {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 28px 20px 20px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}
.git-setup h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
}
.setup-lead,
.setup-next,
.first-commit p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-muted);
}
.setup-next {
  margin-top: 12px;
  font-weight: 600;
  color: var(--text);
}
.setup-steps {
  margin: 0;
  padding: 0 0 0 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--text);
}
.setup-steps code,
.first-commit code {
  display: block;
  margin-top: 4px;
  padding: 4px 7px;
  border-radius: 6px;
  background: var(--code-bg);
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-secondary);
  word-break: break-all;
}
.setup-steps.compact {
  gap: 8px;
  margin-top: 6px;
}
.first-commit {
  margin: 0 10px 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--primary-soft);
  border: var(--border-width) solid color-mix(in srgb, var(--primary) 22%, var(--border));
}
footer {
  border-top: 1px solid var(--border);
  padding: 8px 10px;
  background: var(--bg-elevated);
}
.msg-box {
  position: relative;
}
.msg-ai-wrap {
  position: absolute;
  top: 6px;
  right: 6px;
}
.msg-ai {
  gap: 4px;
  background: var(--bg-elevated);
  box-shadow: 0 0 0 1px var(--border);
}
textarea {
  width: 100%;
  resize: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--text);
  padding: 8px 108px 8px 8px;
  font: inherit;
  font-size: 12.5px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 6px;
}
.act-wrap {
  display: inline-flex;
}
.act-wrap .btn:disabled {
  pointer-events: none;
}
.btn.btn-sm {
  height: 24px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 6px;
}
</style>
