<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import ContextMenu, { type ContextMenuItem } from '@/components/ContextMenu.vue'
import GitGraphRow from '@/panels/GitGraphRow.vue'
import GitCommitDetail from '@/panels/GitCommitDetail.vue'
import GitCommitTreeNode from '@/panels/GitCommitTreeNode.vue'
import GitDiffView from '@/panels/GitDiffView.vue'
import { formatCommitTime, layoutGitGraph, type GitCommit } from '@/utils/gitGraph'
import { buildGitFileTree, collectGitDirPaths } from '@/utils/gitFileTree'

type GitFile = { path: string; code: string; staged: boolean; unstaged: boolean }
type GitStatus = { ok: boolean; error?: string; branch: string; ahead: number; behind: number; files: GitFile[] }
type GitLog = { ok: boolean; error?: string; head: string; commits: GitCommit[] }

const store = useAppStore()
const status = ref<GitStatus | null>(null)
const log = ref<GitLog | null>(null)
const message = ref('')
const error = ref('')
const busy = ref(false)
const selected = ref<Set<string>>(new Set())
const tab = ref<'changes' | 'history'>('changes')
const selectedCommit = ref<GitCommit | null>(null)
const activePath = ref('')
const changePatch = ref('')
const changeDiffError = ref('')
const loadingDiff = ref(false)
const viewMode = ref<'list' | 'tree'>((localStorage.getItem('ca.git.changes.view') as 'list' | 'tree') || 'list')
const treeExpanded = ref<Set<string>>(new Set())
const collapsedDirs = ref<Set<string>>(new Set())
const gitMenu = ref<{ x: number; y: number; path: string; kind: 'file' | 'dir' } | null>(null)

const files = computed(() => status.value?.files || [])
const canCommit = computed(() => Boolean(message.value.trim()) && !busy.value && files.value.some((f) => f.staged || selected.value.has(f.path)))
const graphRows = computed(() => layoutGitGraph(log.value?.commits || []))
const treeRoots = computed(() => buildGitFileTree(files.value.map((file) => ({
  path: file.path,
  status: file.code,
  additions: 0,
  deletions: 0,
}))))
const activeChange = computed(() => files.value.find((file) => file.path === activePath.value) || null)

watch(viewMode, (mode) => {
  localStorage.setItem('ca.git.changes.view', mode)
  if (mode === 'tree') expandAllDirs()
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
  return `${Number(data.ok)}\0${data.branch}\0${data.ahead}\0${data.behind}\0${data.error || ''}\n${files}`
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
    changePatch.value = ''
  } else if (activePath.value && fileSig(prevActive) !== fileSig(nextActive)) {
    void loadChangeDiff(activePath.value, true)
  }
  if (data && !data.ok) error.value = data.error || '不是 Git 仓库'
  else error.value = ''
}

async function refreshLog() {
  if (!store.workspaceId) return
  const data = await api<GitLog>(`/api/workspaces/${store.workspaceId}/git/log?limit=80`)
  if (logKey(data) === logKey(log.value)) return
  log.value = data
}

async function refresh(all = false) {
  if (!store.workspaceId || busy.value) return
  if (inflight) {
    queued = true
    return
  }
  inflight = true
  try {
    do {
      queued = false
      await refreshStatus()
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
  if (document.hidden) return
  void refresh()
}

onMounted(() => {
  void refresh(true)
  pollTimer = window.setInterval(() => {
    if (document.hidden) return
    void refresh()
  }, 4000)
  document.addEventListener('visibilitychange', onVisibility)
})
onUnmounted(() => {
  window.clearInterval(pollTimer)
  window.clearTimeout(debounceTimer)
  document.removeEventListener('visibilitychange', onVisibility)
})

watch(() => store.workspaceId, () => {
  status.value = null
  log.value = null
  selectedCommit.value = null
  activePath.value = ''
  changePatch.value = ''
  void refresh(true)
})
watch(() => store.gitChangedPaths, scheduleRefresh)
watch(tab, (next) => {
  if (next === 'history') void refreshLog()
  else selectedCommit.value = null
})

function toggle(path: string) {
  const next = new Set(selected.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  selected.value = next
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

function showChange(path: string) {
  activePath.value = path
  void loadChangeDiff(path)
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
    { id: 'open-changes', label: '打开更改', icon: 'git', disabled: item.kind === 'dir' && !kids.length },
    { id: 'open-file', label: '打开文件', icon: 'file', disabled: item.kind === 'dir' || deleted },
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
  try {
    error.value = ''
    if (id === 'open-changes') {
      const path = firstFileUnder(item.path, item.kind)
      if (path) showChange(path)
      return
    }
    if (id === 'open-file') {
      openFile(item.path)
      return
    }
    if (id === 'open-head') {
      await store.openRevisionFile(item.path, 'HEAD')
      return
    }
    if (id === 'stage') {
      status.value = await api(`/api/workspaces/${store.workspaceId}/git/stage`, {
        method: 'POST',
        body: JSON.stringify({ paths: [item.path] }),
      })
      void store.loadGitChangedPaths()
      return
    }
    if (id === 'discard') {
      const label = item.kind === 'dir'
        ? `放弃 ${item.path} 下的全部更改？未提交的修改将丢失。`
        : `放弃 ${item.path} 的更改？未提交的修改将丢失。`
      const ok = await store.askConfirm({
        title: '放弃更改',
        summary: label,
        confirmLabel: '放弃',
        danger: true,
      })
      if (!ok) return
      status.value = await api(`/api/workspaces/${store.workspaceId}/git/discard`, {
        method: 'POST',
        body: JSON.stringify({ paths: [item.path] }),
      })
      void store.loadGitChangedPaths()
      if (activePath.value === item.path || activePath.value.startsWith(`${item.path.replace(/\/$/, '')}/`)) {
        activePath.value = ''
        changePatch.value = ''
      }
      return
    }
    if (id === 'ignore') {
      status.value = await api(`/api/workspaces/${store.workspaceId}/git/ignore`, {
        method: 'POST',
        body: JSON.stringify({ paths: [item.path] }),
      })
      void store.loadGitChangedPaths()
      return
    }
    if (id === 'reveal') {
      store.openExplorerPanel()
      await store.revealInTree(item.path)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

function mark(code: string) {
  if (code.includes('?')) return '未跟踪'
  if (code.includes('D')) return '删除'
  if (code.includes('A')) return '新增'
  if (code.includes('M')) return '修改'
  if (code.includes('U')) return '冲突'
  return code.trim() || '改动'
}

async function run(label: string, fn: () => Promise<void>) {
  const ok = await store.askConfirm({
    title: '确认 Git 操作',
    summary: label,
    confirmLabel: '继续',
    danger: true,
  })
  if (!ok) return
  busy.value = true
  error.value = ''
  try {
    await fn()
    await refresh(true)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
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
  await run(`提交：${msg}`, async () => {
    status.value = await api(`/api/workspaces/${store.workspaceId}/git/commit`, {
      method: 'POST',
      body: JSON.stringify({ message: msg, paths }),
    })
    message.value = ''
    selected.value = new Set()
    void store.loadGitChangedPaths()
  })
}

async function push() {
  const branch = status.value?.branch || 'HEAD'
  await run(`推送当前分支 ${branch} 到 origin`, async () => {
    status.value = await api(`/api/workspaces/${store.workspaceId}/git/push`, {
      method: 'POST',
      body: JSON.stringify({ remote: 'origin' }),
    })
  })
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
      <span class="branch">
        <AppIcon name="git" :size="14" />
        {{ status?.branch || 'Git' }}
      </span>
      <span v-if="status?.ahead" class="pill">↑{{ status.ahead }}</span>
      <span v-if="status?.behind" class="pill">↓{{ status.behind }}</span>
      <span class="spacer" />
      <div class="seg" role="tablist" aria-label="Git 视图">
        <button
          type="button"
          role="tab"
          :aria-selected="tab === 'changes'"
          :class="{ on: tab === 'changes' }"
          @click="tab = 'changes'"
        >
          更改
          <span v-if="files.length" class="seg-count">{{ files.length }}</span>
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="tab === 'history'"
          :class="{ on: tab === 'history' }"
          @click="tab = 'history'"
        >
          历史
        </button>
      </div>
      <template v-if="tab === 'changes'">
        <button
          type="button"
          class="icon-btn icon-btn-ghost"
          :class="{ active: viewMode === 'list' }"
          title="普通列表"
          @click="viewMode = 'list'"
        >
          <AppIcon name="list" :size="14" />
        </button>
        <button
          type="button"
          class="icon-btn icon-btn-ghost"
          :class="{ active: viewMode === 'tree' }"
          title="树形展示"
          @click="viewMode = 'tree'"
        >
          <AppIcon name="tree" :size="14" />
        </button>
      </template>
      <button type="button" class="icon-btn icon-btn-ghost" title="刷新" @click="refresh(true)">
        <AppIcon name="refresh" :size="14" />
      </button>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
    <div v-if="tab === 'changes'" class="changes" :class="{ 'has-diff': !!activeChange }">
      <div class="files">
        <template v-if="viewMode === 'list'">
          <div
            v-for="file in files"
            :key="file.path"
            class="row"
            :class="{ on: activePath === file.path }"
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
          @toggle="toggleTreeDir"
          @select="showChange"
          @open="openFile"
          @check="toggle"
          @context="onContext"
        />
        <p v-if="status?.ok && !files.length" class="empty">工作区干净</p>
      </div>
      <div v-if="activeChange" class="diff-pane">
        <div class="diff-head">
          <span>{{ mark(activeChange.code) }} · {{ activeChange.path }}</span>
          <span v-if="activeChange.staged && !activeChange.unstaged" class="pill">已暂存</span>
        </div>
        <p v-if="changeDiffError" class="err">{{ changeDiffError }}</p>
        <p v-else-if="loadingDiff" class="empty">加载 diff…</p>
        <GitDiffView v-else :patch="changePatch" />
      </div>
    </div>
    <GitCommitDetail
      v-else-if="selectedCommit && store.workspaceId"
      :workspace-id="store.workspaceId"
      :rev="selectedCommit.hash"
      :preview="selectedCommit"
      @back="selectedCommit = null"
      @open-file="openFile"
    />
    <div v-else class="history">
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
            <span class="subject">{{ row.subject || '(无说明)' }}</span>
            <span v-for="refName in row.refs" :key="refName" class="ref" :class="{ head: refName === 'HEAD' }">{{ refName }}</span>
          </span>
          <span class="meta">{{ row.author }} · {{ formatCommitTime(row.date) }} · {{ row.short }}</span>
        </span>
      </button>
      <p v-if="log?.ok && !graphRows.length" class="empty">暂无提交</p>
    </div>
    <footer v-if="tab === 'changes'">
      <textarea v-model="message" rows="3" placeholder="提交说明" />
      <div class="actions">
        <button type="button" class="btn" :disabled="!selected.size || busy" @click="stageSelected">暂存所选</button>
        <button type="button" class="btn btn-primary" :disabled="!canCommit" @click="commit">提交</button>
        <button type="button" class="btn" :disabled="busy || !status?.ok" @click="push">推送</button>
      </div>
    </footer>
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
.git { overflow: hidden; }
.git-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 6px 10px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--panel-bg);
  flex-shrink: 0;
}
.git-bar .spacer { margin-left: auto; }
.branch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 600;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pill {
  font-size: 11px;
  color: var(--primary);
  background: var(--code-bg);
  border-radius: 999px;
  padding: 1px 7px;
  flex-shrink: 0;
}
.seg {
  display: inline-flex;
  align-items: center;
  padding: 2px;
  gap: 2px;
  flex-shrink: 0;
  border-radius: 8px;
  background: var(--code-bg);
  border: var(--border-width) solid var(--border);
}
.seg button {
  height: 22px;
  padding: 0 10px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  line-height: 1;
}
.seg button:hover:not(.on) {
  color: var(--text-h);
}
.seg button.on {
  background: var(--bg-elevated);
  color: var(--text-h);
  box-shadow: 0 1px 0 color-mix(in srgb, var(--border) 70%, transparent);
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
  padding: 6px 0;
}
.changes.has-diff .files {
  flex: 0 0 auto;
  max-height: 42%;
  border-bottom: var(--border-width) solid var(--border);
}
.row,
.commit {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  background: transparent;
  color: var(--text);
  padding: 6px 12px;
  cursor: pointer;
  text-align: left;
  font-size: 12.5px;
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
  padding: 6px 12px;
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.commit {
  align-items: stretch;
  padding: 0 10px 0 6px;
  min-height: 40px;
}
.row:hover,
.commit:hover { background: var(--bg-muted); }
.row.on,
.commit.head { background: var(--primary-soft); }
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
footer {
  border-top: 1px solid var(--border);
  padding: 10px;
  background: var(--bg-elevated);
}
textarea {
  width: 100%;
  resize: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--text);
  padding: 8px;
  font: inherit;
  font-size: 12.5px;
}
.actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.btn { height: 28px; padding: 0 10px; font-size: 12px; }
.icon-btn { width: 28px; height: 28px; }
</style>
