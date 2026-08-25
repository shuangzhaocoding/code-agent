<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api/http'
import AppIcon from '@/components/AppIcon.vue'
import GitDiffView from '@/panels/GitDiffView.vue'
import GitCommitTreeNode from '@/panels/GitCommitTreeNode.vue'
import { formatCommitTime, type GitCommit } from '@/utils/gitGraph'
import { buildGitFileTree, collectGitDirPaths } from '@/utils/gitFileTree'

export type CommitFile = {
  path: string
  old_path: string
  status: string
  additions: number
  deletions: number
  binary: boolean
  truncated: boolean
  patch: string
}

const props = defineProps<{
  workspaceId: string
  rev: string
  preview?: GitCommit | null
}>()

const emit = defineEmits<{
  back: []
  openFile: [path: string]
}>()

const loading = ref(false)
const error = ref('')
const commit = ref<GitCommit | null>(props.preview || null)
const files = ref<CommitFile[]>([])
const activePath = ref('')
const viewMode = ref<'list' | 'tree'>((localStorage.getItem('ca.git.commit.view') as 'list' | 'tree') || 'list')
const treeExpanded = ref<Set<string>>(new Set())

const activeFile = computed(() => files.value.find((file) => file.path === activePath.value) || null)
const header = computed(() => commit.value || props.preview || null)
const treeRoots = computed(() => buildGitFileTree(files.value))

watch(viewMode, (mode) => {
  localStorage.setItem('ca.git.commit.view', mode)
  if (mode === 'tree') expandAllDirs()
})

watch(treeRoots, () => {
  if (viewMode.value === 'tree') expandAllDirs()
})

function expandAllDirs() {
  treeExpanded.value = new Set(collectGitDirPaths(treeRoots.value))
}

function toggleTreeDir(path: string) {
  const next = new Set(treeExpanded.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  treeExpanded.value = next
}

function statusLabel(code: string) {
  if (code === 'A') return '新增'
  if (code === 'D') return '删除'
  if (code === 'R') return '重命名'
  return '修改'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api<{ ok: boolean; error?: string; commit: GitCommit; files: CommitFile[] }>(
      `/api/workspaces/${props.workspaceId}/git/commits/${encodeURIComponent(props.rev)}`,
    )
    commit.value = data.commit
    files.value = data.files || []
    activePath.value = files.value[0]?.path || ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

watch(() => [props.workspaceId, props.rev], load, { immediate: true })

async function copyHash() {
  const hash = header.value?.hash
  if (!hash) return
  try {
    await navigator.clipboard.writeText(hash)
  } catch {
    /* ignore */
  }
}
</script>

<template>
  <div class="detail">
    <div class="detail-bar">
      <button type="button" class="back" @click="emit('back')">
        <AppIcon name="arrow-left" :size="14" />
        返回
      </button>
      <button v-if="header" type="button" class="hash" :title="header.hash" @click="copyHash">{{ header.short }}</button>
      <span class="spacer" />
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
    </div>
    <div v-if="header" class="header">
      <strong class="subject">{{ header.subject || '(无说明)' }}</strong>
      <span class="meta">{{ header.author }} · {{ formatCommitTime(header.date) }}</span>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
    <p v-else-if="loading" class="empty">加载 diff…</p>
    <p v-else-if="!files.length" class="empty">该提交没有文件变更</p>
    <template v-else>
      <div class="files">
        <template v-if="viewMode === 'list'">
          <button
            v-for="file in files"
            :key="file.path"
            type="button"
            class="file"
            :class="{ on: file.path === activePath }"
            @click="activePath = file.path"
            @dblclick="emit('openFile', file.path)"
          >
            <span class="code">{{ file.status }}</span>
            <span class="path" :title="file.old_path ? `${file.old_path} → ${file.path}` : file.path">
              {{ file.old_path ? `${file.old_path} → ${file.path}` : file.path }}
            </span>
            <span class="stats">
              <em v-if="file.additions" class="add">+{{ file.additions }}</em>
              <em v-if="file.deletions" class="del">-{{ file.deletions }}</em>
              <em v-if="file.binary" class="bin">二进制</em>
            </span>
          </button>
        </template>
        <template v-else>
          <GitCommitTreeNode
            v-for="node in treeRoots"
            :key="node.path"
            :node="node"
            :depth="0"
            :expanded="treeExpanded"
            :active-path="activePath"
            @toggle="toggleTreeDir"
            @select="(path) => activePath = path"
            @open="(path) => emit('openFile', path)"
          />
        </template>
      </div>
      <div v-if="activeFile" class="diff-pane">
        <div class="diff-head">
          <span>{{ statusLabel(activeFile.status) }} · {{ activeFile.path }}</span>
          <span v-if="activeFile.truncated" class="warn">已截断</span>
        </div>
        <GitDiffView :patch="activeFile.patch" :binary="activeFile.binary" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.detail {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.detail-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  flex-shrink: 0;
}
.back,
.hash {
  border: 0;
  background: transparent;
  cursor: pointer;
  color: var(--primary);
  font-size: 12px;
  padding: 4px 6px;
  border-radius: 6px;
}
.back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.hash {
  font-family: var(--mono);
  color: var(--text-muted);
}
.spacer { margin-left: auto; }
.icon-btn { width: 28px; height: 28px; flex-shrink: 0; }
.back:hover,
.hash:hover { background: var(--bg-muted); }
.header {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 12px 8px;
  flex-shrink: 0;
}
.subject {
  font-size: 13px;
  color: var(--text-h);
}
.meta {
  font-size: 11px;
  color: var(--text-muted);
}
.err {
  margin: 0;
  padding: 8px 12px;
  color: var(--danger);
  font-size: 12px;
}
.empty {
  margin: 16px 12px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}
.files {
  flex: 0 0 auto;
  max-height: 36%;
  overflow: auto;
  border-top: var(--border-width) solid var(--border);
  border-bottom: var(--border-width) solid var(--border);
}
.file {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  background: transparent;
  color: var(--text);
  padding: 5px 12px;
  cursor: pointer;
  text-align: left;
  font-size: 12px;
}
.file:hover { background: var(--bg-muted); }
.file.on { background: var(--primary-soft); }
.code {
  font-family: var(--mono);
  width: 14px;
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
}
.stats {
  display: inline-flex;
  gap: 6px;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  font-style: normal;
}
.stats em { font-style: normal; }
.add { color: #059669; }
.del { color: var(--error-text); }
.bin { color: var(--text-muted); font-weight: 500; }
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
.warn { color: var(--primary); }
</style>
