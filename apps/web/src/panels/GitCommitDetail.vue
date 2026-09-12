<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api/http'
import { t } from '@/i18n'
import { useAppStore } from '@/stores/app'
import { useGitDiffTarget } from '@/composables/useGitDiffTarget'
import type { GitDiffTarget } from '@/utils/gitPrefs'
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

const store = useAppStore()
const { diffTarget, setDiffTarget } = useGitDiffTarget()
const loading = ref(false)
const error = ref('')
const commit = ref<GitCommit | null>(props.preview || null)
const files = ref<CommitFile[]>([])
const activePath = ref('')
const showPanelDiff = ref(false)
const viewMode = ref<'list' | 'tree'>((localStorage.getItem('ca.git.commit.view') as 'list' | 'tree') || 'list')
const diffLayout = ref<'down' | 'right'>((localStorage.getItem('ca.git.commit.layout') as 'down' | 'right') || 'down')
const treeExpanded = ref<Set<string>>(new Set())

const activeFile = computed(() => files.value.find((file) => file.path === activePath.value) || null)
const header = computed(() => commit.value || props.preview || null)
const treeRoots = computed(() => buildGitFileTree(files.value))

watch(viewMode, (mode) => {
  localStorage.setItem('ca.git.commit.view', mode)
  if (mode === 'tree') expandAllDirs()
})
watch(diffLayout, (mode) => {
  localStorage.setItem('ca.git.commit.layout', mode)
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

function closeDiff() {
  showPanelDiff.value = false
  activePath.value = ''
}

function selectFile(path: string, force?: GitDiffTarget) {
  activePath.value = path
  const mode = force || diffTarget.value
  if (mode === 'editor') {
    showPanelDiff.value = false
    void openDiffInEditor(path)
    return
  }
  showPanelDiff.value = true
}

function chooseDiffTarget(mode: GitDiffTarget) {
  setDiffTarget(mode)
  if (mode === 'editor') {
    showPanelDiff.value = false
    if (activePath.value) void openDiffInEditor(activePath.value)
    return
  }
  if (!activePath.value && files.value[0]) activePath.value = files.value[0].path
  showPanelDiff.value = Boolean(activePath.value)
}

async function openDiffInEditor(path?: string) {
  const target = path || activePath.value
  if (!target) return
  await store.openWorkingDiff(target)
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
    const first = files.value[0]?.path || ''
    if (diffTarget.value === 'panel') {
      activePath.value = first
      showPanelDiff.value = Boolean(first)
    } else {
      activePath.value = ''
      showPanelDiff.value = false
    }
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
        <AppIcon name="arrow-left" :size="16" :stroke-width="1.75" />
        返回
      </button>
      <button v-if="header" type="button" class="hash" :title="header.hash" @click="copyHash">{{ header.short }}</button>
      <span class="spacer" />
      <button
        type="button"
        class="ghost-icon-btn"
        :class="{ active: viewMode === 'list' }"
        title="普通列表"
        @click="viewMode = 'list'"
      >
        <AppIcon name="list" :size="16" :stroke-width="1.75" />
      </button>
      <button
        type="button"
        class="ghost-icon-btn"
        :class="{ active: viewMode === 'tree' }"
        title="树形展示"
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
    </div>
    <div v-if="header" class="header">
      <strong class="subject">{{ header.subject || '(无说明)' }}</strong>
      <span class="meta">{{ header.author }} · {{ formatCommitTime(header.date) }}</span>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
    <p v-else-if="loading" class="empty">加载 diff…</p>
    <p v-else-if="!files.length" class="empty">该提交没有文件变更</p>
    <template v-else>
      <div
        class="split"
        :class="{ 'has-diff': showPanelDiff && !!activeFile, 'diff-right': diffLayout === 'right', 'diff-down': diffLayout === 'down' }"
      >
      <div class="files">
        <template v-if="viewMode === 'list'">
          <button
            v-for="file in files"
            :key="file.path"
            type="button"
            class="file"
            :class="{ on: file.path === activePath }"
            @click="selectFile(file.path)"
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
            @select="selectFile"
            @open="(path) => emit('openFile', path)"
          />
        </template>
      </div>
      <div v-if="showPanelDiff && activeFile" class="diff-pane">
        <div class="diff-head">
          <span class="diff-title">{{ statusLabel(activeFile.status) }} · {{ activeFile.path }}</span>
          <span class="diff-head-actions">
            <span v-if="activeFile.truncated" class="warn">{{ t('git.truncated') }}</span>
            <button
              type="button"
              class="ghost-icon-btn"
              :class="{ active: diffLayout === 'down' }"
              :title="t('git.layoutDown')"
              @click="diffLayout = 'down'"
            >
              <AppIcon name="panel-bottom" :size="14" :stroke-width="1.75" />
            </button>
            <button
              type="button"
              class="ghost-icon-btn"
              :class="{ active: diffLayout === 'right' }"
              :title="t('git.layoutRight')"
              @click="diffLayout = 'right'"
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
        <GitDiffView :patch="activeFile.patch" :binary="activeFile.binary" />
      </div>
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
.split {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.split.has-diff.diff-right {
  flex-direction: row;
}
.files {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border-top: var(--border-width) solid var(--border);
}
.split.has-diff.diff-down .files {
  flex: 0 0 auto;
  max-height: 36%;
  border-bottom: var(--border-width) solid var(--border);
}
.split.has-diff.diff-right .files {
  flex: 0 0 36%;
  max-height: none;
  min-width: 148px;
  max-width: 52%;
  border-right: var(--border-width) solid var(--border);
  border-bottom: 0;
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
.warn { color: var(--primary); }
</style>
