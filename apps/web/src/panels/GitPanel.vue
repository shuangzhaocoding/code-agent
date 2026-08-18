<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'

type GitFile = { path: string; code: string; staged: boolean; unstaged: boolean }
type GitStatus = { ok: boolean; error?: string; branch: string; ahead: number; behind: number; files: GitFile[] }

const store = useAppStore()
const status = ref<GitStatus | null>(null)
const message = ref('')
const error = ref('')
const busy = ref(false)
const selected = ref<Set<string>>(new Set())

const files = computed(() => status.value?.files || [])
const canCommit = computed(() => Boolean(message.value.trim()) && !busy.value && files.value.some((f) => f.staged || selected.value.has(f.path)))

async function refresh() {
  if (!store.workspaceId) return
  error.value = ''
  try {
    status.value = await api<GitStatus>(`/api/workspaces/${store.workspaceId}/git/status`)
    if (status.value && !status.value.ok) error.value = status.value.error || '不是 Git 仓库'
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

onMounted(refresh)
watch(() => store.workspaceId, refresh)

function toggle(path: string) {
  const next = new Set(selected.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  selected.value = next
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
    await refresh()
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
</script>

<template>
  <div class="panel-shell git">
    <header class="panel-head">
      <span class="branch">
        <AppIcon name="git" :size="14" />
        {{ status?.branch || 'Git' }}
      </span>
      <span v-if="status?.ahead" class="pill">↑{{ status.ahead }}</span>
      <span v-if="status?.behind" class="pill">↓{{ status.behind }}</span>
      <span class="spacer" />
      <button type="button" class="icon-btn" title="刷新" @click="refresh">
        <AppIcon name="refresh" :size="14" />
      </button>
    </header>
    <p v-if="error" class="err">{{ error }}</p>
    <div class="files">
      <button
        v-for="file in files"
        :key="file.path"
        type="button"
        class="row"
        :class="{ on: selected.has(file.path) }"
        @click="toggle(file.path)"
        @dblclick="openFile(file.path)"
      >
        <span class="code">{{ file.code }}</span>
        <span class="path">{{ file.path }}</span>
        <span class="tag">{{ mark(file.code) }}</span>
      </button>
      <p v-if="status?.ok && !files.length" class="empty">工作区干净</p>
    </div>
    <footer>
      <textarea v-model="message" rows="3" placeholder="提交说明" />
      <div class="actions">
        <button type="button" class="btn" :disabled="!selected.size || busy" @click="stageSelected">暂存所选</button>
        <button type="button" class="btn btn-primary" :disabled="!canCommit" @click="commit">提交</button>
        <button type="button" class="btn" :disabled="busy || !status?.ok" @click="push">推送</button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.git { overflow: hidden; }
.branch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 600;
}
.pill {
  font-size: 11px;
  color: var(--primary);
  background: var(--primary-soft);
  border-radius: 999px;
  padding: 1px 7px;
}
.err {
  margin: 0;
  padding: 8px 12px;
  color: var(--danger);
  font-size: 12px;
}
.files {
  flex: 1;
  overflow: auto;
  padding: 6px 0 10px;
}
.row {
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
.row:hover { background: var(--bg-muted); }
.row.on { background: var(--primary-soft); }
.code {
  font-family: var(--mono);
  width: 24px;
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
.tag { color: var(--text-muted); font-size: 11px; flex-shrink: 0; }
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
