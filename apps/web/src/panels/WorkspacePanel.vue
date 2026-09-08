<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useAppStore, type Conversation, type Workspace } from '@/stores/app'
import { api } from '@/api/http'
import AppIcon from '@/components/AppIcon.vue'
import WorkspaceSwitch from '@/components/WorkspaceSwitch.vue'
import { useSessionPins } from '@/composables/useSessionPins'
import { formatRelativeTime } from '@/utils/relativeTime'

const PREVIEW_LIMIT = 5

const store = useAppStore()
const pins = useSessionPins()
const showOpen = ref(false)
const expandedIds = ref<Set<string>>(new Set())
const showAllIds = ref<Set<string>>(new Set())
const convMap = reactive<Record<string, Conversation[]>>({})
const loading = reactive<Record<string, boolean>>({})
const errors = reactive<Record<string, string>>({})
const openingId = ref<string | null>(null)
const switchingId = ref<string | null>(null)
const creatingId = ref<string | null>(null)
const editingId = ref<string | null>(null)
const editingTitle = ref('')
const pinTick = ref(0)

onMounted(async () => {
  await store.loadWorkspaces()
  if (store.workspaceId) await setExpanded(store.workspaceId, true)
})

watch(
  () => store.conversations,
  (list) => {
    if (store.workspaceId) convMap[store.workspaceId] = [...list]
  },
  { deep: true },
)

function isExpanded(id: string) {
  return expandedIds.value.has(id)
}

function showsAll(id: string) {
  return showAllIds.value.has(id)
}

function basename(path: string) {
  const parts = path.replace(/[\\/]+$/, '').split(/[\\/]/)
  return parts[parts.length - 1] || path
}

async function setExpanded(id: string, open: boolean) {
  const next = new Set(expandedIds.value)
  if (open) next.add(id)
  else {
    next.delete(id)
    const all = new Set(showAllIds.value)
    all.delete(id)
    showAllIds.value = all
  }
  expandedIds.value = next
  if (open) await loadConvs(id)
}

async function toggleExpand(id: string) {
  await setExpanded(id, !isExpanded(id))
}

function toggleShowAll(id: string) {
  const next = new Set(showAllIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  showAllIds.value = next
}

async function loadConvs(wsId: string) {
  loading[wsId] = true
  errors[wsId] = ''
  try {
    convMap[wsId] = await api<Conversation[]>(`/api/workspaces/${wsId}/conversations`)
  } catch (err) {
    errors[wsId] = err instanceof Error ? err.message : String(err)
  } finally {
    loading[wsId] = false
  }
}

function sortedConvs(wsId: string) {
  void pinTick.value
  return pins.sortByPinIn(wsId, convMap[wsId] || [])
}

function visibleConvs(wsId: string) {
  const list = sortedConvs(wsId)
  if (showsAll(wsId) || list.length <= PREVIEW_LIMIT) return list
  return list.slice(0, PREVIEW_LIMIT)
}

function hiddenCount(wsId: string) {
  const n = sortedConvs(wsId).length - PREVIEW_LIMIT
  return n > 0 && !showsAll(wsId) ? n : 0
}

async function openWorkspace(ws: Workspace, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (switchingId.value || ws.id === store.workspaceId) return
  switchingId.value = ws.id
  try {
    await store.selectWorkspace(ws.id, { openExplorer: false })
    await setExpanded(ws.id, true)
  } finally {
    switchingId.value = null
  }
}

async function newSession(ws: Workspace, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (creatingId.value) return
  creatingId.value = ws.id
  try {
    if (store.workspaceId !== ws.id) {
      await store.selectWorkspace(ws.id, { openExplorer: false })
    }
    await setExpanded(ws.id, true)
    await store.newChat()
    window.dispatchEvent(new Event('ca-focus-agent'))
  } finally {
    creatingId.value = null
  }
}

async function openConv(ws: Workspace, conv: Conversation) {
  if (openingId.value || editingId.value === conv.id) return
  openingId.value = conv.id
  try {
    if (store.workspaceId !== ws.id) {
      await store.selectWorkspace(ws.id, { openExplorer: false })
    }
    if (store.conversationId !== conv.id) {
      await store.openConversation(conv.id)
    }
    window.dispatchEvent(new Event('ca-focus-agent'))
  } finally {
    openingId.value = null
  }
}

function turnCount(wsId: string, item: Conversation) {
  if (wsId === store.workspaceId && item.id === store.conversationId) {
    return store.messages.filter((m) => m.role === 'user').length
  }
  return item.turn_count ?? 0
}

function sessionStatus(wsId: string, item: Conversation): { label: string; tone: string; icon: string } | null {
  let label: string | null = null
  if (wsId === store.workspaceId && item.id === store.conversationId) {
    if (store.pendingApprovals.length) label = '工具确认'
    else if (store.isRunBusy()) label = store.runStatus === 'queued' ? '排队中' : '生成中'
  } else if (item.awaiting_approval) {
    label = '工具确认'
  } else if (item.active_run_id) {
    if (item.run_status === 'queued') label = '排队中'
    else if (!item.run_status || item.run_status === 'running') label = '生成中'
  }
  if (!label) return null
  if (label === '工具确认') return { label, tone: 'confirm', icon: 'shield' }
  if (label === '排队中') return { label, tone: 'queued', icon: 'clock' }
  return { label, tone: 'running', icon: 'loader' }
}

const statusByKey = computed(() => {
  const map = new Map<string, { label: string; tone: string; icon: string }>()
  for (const ws of store.recentWorkspaces) {
    if (!isExpanded(ws.id)) continue
    for (const item of convMap[ws.id] || []) {
      const status = sessionStatus(ws.id, item)
      if (status) map.set(`${ws.id}:${item.id}`, status)
    }
  }
  return map
})

function onTogglePin(wsId: string, id: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  pins.toggleIn(wsId, id)
  pinTick.value += 1
}

async function onDelete(wsId: string, id: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (editingId.value === id) cancelRename()
  if (pins.isPinnedIn(wsId, id)) pins.toggleIn(wsId, id)
  pinTick.value += 1

  if (wsId === store.workspaceId) {
    await store.deleteConversation(id)
    return
  }

  await api(`/api/conversations/${id}`, { method: 'DELETE' })
  convMap[wsId] = (convMap[wsId] || []).filter((c) => c.id !== id)
}

function startRename(item: Conversation, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  editingId.value = item.id
  editingTitle.value = item.title
  void nextTick(() => {
    const el = document.querySelector<HTMLInputElement>('.conv-rename-input')
    el?.focus()
    el?.select()
  })
}

async function commitRename(wsId: string, id: string) {
  if (editingId.value !== id) return
  const title = editingTitle.value.trim()
  editingId.value = null
  editingTitle.value = ''
  if (!title) return

  if (wsId === store.workspaceId) {
    await store.renameConversation(id, title)
    return
  }

  const row = (convMap[wsId] || []).find((c) => c.id === id)
  if (!row || row.title === title) return
  await api(`/api/conversations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
  convMap[wsId] = (convMap[wsId] || []).map((c) => (c.id === id ? { ...c, title } : c))
}

function cancelRename() {
  editingId.value = null
  editingTitle.value = ''
}

function onRenameKeydown(wsId: string, id: string, e: KeyboardEvent) {
  e.stopPropagation()
  if (e.key === 'Enter') {
    e.preventDefault()
    void commitRename(wsId, id)
    return
  }
  if (e.key === 'Escape') {
    e.preventDefault()
    cancelRename()
  }
}
</script>

<template>
  <div class="panel-shell workspace-panel panel-chromeless">
    <header class="ws-head">
      <span class="ws-head-title">工作空间</span>
      <button type="button" class="ws-head-btn" title="打开工作空间" @click="showOpen = true">
        <AppIcon name="plus" :size="14" :stroke-width="1.75" />
        <span>打开</span>
      </button>
    </header>

    <div class="workspace-body">
      <p v-if="!store.recentWorkspaces.length" class="empty">还没有工作空间，点右上角打开一个目录。</p>

      <ul class="ws-list">
        <li
          v-for="ws in store.recentWorkspaces"
          :key="ws.id"
          class="ws-group"
          :class="{ current: ws.id === store.workspaceId, open: isExpanded(ws.id) }"
        >
          <div class="ws-row" :title="ws.root_path">
            <button type="button" class="ws-main" @click="toggleExpand(ws.id)">
              <AppIcon
                class="ws-chev"
                :name="isExpanded(ws.id) ? 'chevron-down' : 'chevron-right'"
                :size="12"
                :stroke-width="2"
              />
              <span class="ws-copy">
                <span class="ws-name">{{ ws.name || basename(ws.root_path) }}</span>
              </span>
            </button>
            <div class="ws-end">
              <div class="ws-tools">
                <button
                  type="button"
                  class="ws-tool"
                  title="新建会话"
                  :disabled="creatingId === ws.id"
                  @click="newSession(ws, $event)"
                >
                  <AppIcon name="plus" :size="13" :stroke-width="1.75" />
                </button>
                <button
                  v-if="ws.id !== store.workspaceId"
                  type="button"
                  class="ws-tool text"
                  :disabled="switchingId === ws.id"
                  @click="openWorkspace(ws, $event)"
                >
                  打开
                </button>
              </div>
              <span v-if="ws.id === store.workspaceId" class="ws-dot" title="当前工作空间" />
            </div>
          </div>

          <div v-if="isExpanded(ws.id)" class="ws-sessions">
            <p v-if="loading[ws.id]" class="hint">加载中…</p>
            <p v-else-if="errors[ws.id]" class="hint err">{{ errors[ws.id] }}</p>
            <p v-else-if="!sortedConvs(ws.id).length" class="hint">暂无会话</p>

            <div
              v-for="conv in visibleConvs(ws.id)"
              :key="conv.id"
              class="conv-row"
              :class="{
                active: conv.id === store.conversationId && ws.id === store.workspaceId,
                pinned: pins.isPinnedIn(ws.id, conv.id),
              }"
              @click="openConv(ws, conv)"
            >
              <span class="conv-status-slot" aria-hidden="true">
                <template v-for="st in [statusByKey.get(`${ws.id}:${conv.id}`)]" :key="`${conv.id}-status`">
                  <span
                    v-if="st"
                    class="conv-status"
                    :class="st.tone"
                    :title="st.label"
                    :aria-label="st.label"
                  >
                    <AppIcon :name="st.icon" :size="12" :stroke-width="1.75" />
                  </span>
                </template>
              </span>

              <span class="conv-copy">
                <input
                  v-if="editingId === conv.id"
                  v-model="editingTitle"
                  class="conv-rename-input"
                  type="text"
                  maxlength="300"
                  aria-label="重命名"
                  @click.stop
                  @keydown="onRenameKeydown(ws.id, conv.id, $event)"
                  @blur="commitRename(ws.id, conv.id)"
                />
                <span v-else class="conv-title" :title="conv.title">{{ conv.title }}</span>
              </span>

              <span class="conv-meta">
                <span v-if="!editingId" class="conv-time">
                  {{ formatRelativeTime(conv.updated_at || conv.created_at) }}
                </span>
              </span>

              <span class="conv-actions">
                <button type="button" class="conv-action" title="重命名" @click="startRename(conv, $event)">
                  <AppIcon name="pencil" :size="13" :stroke-width="1.75" />
                </button>
                <button
                  type="button"
                  class="conv-action"
                  :class="{ on: pins.isPinnedIn(ws.id, conv.id) }"
                  :title="pins.isPinnedIn(ws.id, conv.id) ? '取消置顶' : '置顶'"
                  @click="onTogglePin(ws.id, conv.id, $event)"
                >
                  <AppIcon name="pin" :size="13" :stroke-width="1.75" />
                </button>
                <button type="button" class="conv-action danger" title="删除会话" @click="onDelete(ws.id, conv.id, $event)">
                  <AppIcon name="trash" :size="13" :stroke-width="1.75" />
                </button>
              </span>

              <span class="conv-turns">{{ turnCount(ws.id, conv) }}轮</span>
            </div>

            <button
              v-if="hiddenCount(ws.id)"
              type="button"
              class="show-more"
              @click="toggleShowAll(ws.id)"
            >
              显示更多（{{ hiddenCount(ws.id) }}）
            </button>
            <button
              v-else-if="showsAll(ws.id) && sortedConvs(ws.id).length > PREVIEW_LIMIT"
              type="button"
              class="show-more"
              @click="toggleShowAll(ws.id)"
            >
              收起
            </button>
          </div>
        </li>
      </ul>
    </div>

    <WorkspaceSwitch v-if="showOpen" @close="showOpen = false" />
  </div>
</template>

<style scoped>
.workspace-panel {
  background: var(--panel-bg);
}

.ws-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 4px 10px 2px 12px;
  flex-shrink: 0;
}

.ws-head-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.ws-head-btn {
  margin-left: auto;
  height: 26px;
  padding: 0 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.ws-head-btn:hover {
  background: var(--code-bg);
  color: var(--text-h);
}

.workspace-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px 8px 12px;
}

.empty,
.hint {
  margin: 8px 6px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.45;
}

.hint.err {
  color: var(--error-text);
}

.ws-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ws-group {
  border-radius: 10px;
}

.ws-row {
  display: flex;
  align-items: center;
  min-height: 30px;
  padding-right: 6px;
  border-radius: 10px;
}

.ws-row:hover,
.ws-group.current > .ws-row {
  background: color-mix(in srgb, var(--text-h) 4.5%, transparent);
}

.ws-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 4px 4px 4px 8px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--text-h);
  text-align: left;
  cursor: pointer;
  font: inherit;
}

.ws-chev {
  flex-shrink: 0;
  color: var(--text-muted);
  opacity: 0.85;
}

.ws-copy {
  min-width: 0;
  flex: 1;
}

.ws-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
  line-height: 17px;
}

.ws-dot {
  width: 6px;
  height: 6px;
  margin: 0 4px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
}

.ws-end {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  min-height: 22px;
}

.ws-tools {
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}

.ws-row:hover .ws-tools,
.ws-row:focus-within .ws-tools {
  opacity: 1;
  pointer-events: auto;
}

.ws-tool {
  height: 22px;
  min-width: 22px;
  padding: 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  display: grid;
  place-items: center;
  cursor: pointer;
}

.ws-tool.text {
  padding: 0 8px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
}

.ws-tool:hover {
  background: var(--code-bg);
  color: var(--text-h);
}

.ws-tool:disabled {
  opacity: 0.45;
  cursor: default;
}

.ws-sessions {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 1px 0 6px;
}

.conv-row {
  position: relative;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 4px 8px 4px 10px;
  border-radius: 10px;
  color: var(--text);
  cursor: pointer;
}

.conv-row:hover {
  background: color-mix(in srgb, var(--text-h) 4.5%, transparent);
  color: var(--text-h);
}

.conv-row.active {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  color: var(--text-h);
}

.conv-row.active .conv-title {
  color: var(--text-h);
  font-weight: 600;
}

.conv-status-slot {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
}

.conv-status {
  width: 14px;
  height: 14px;
  display: grid;
  place-items: center;
  color: var(--text-muted);
}

.conv-status.running {
  color: var(--primary);
}

.conv-status.running :deep(svg) {
  animation: conv-spin 0.9s linear infinite;
}

.conv-status.confirm {
  color: var(--danger);
}

.conv-status.queued {
  color: var(--text-muted);
}

@keyframes conv-spin {
  to {
    transform: rotate(360deg);
  }
}

.conv-copy {
  min-width: 0;
  flex: 1;
}

.conv-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 500;
  line-height: 17px;
}

.conv-rename-input {
  width: 100%;
  min-width: 0;
  height: 22px;
  padding: 0 6px;
  border: var(--border-width) solid color-mix(in srgb, var(--primary) 40%, var(--border));
  border-radius: 6px;
  background: var(--panel-bg);
  color: var(--text-h);
  font: inherit;
  font-size: 12px;
  outline: none;
}

.conv-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.conv-turns {
  flex-shrink: 0;
  min-width: 2.5rem;
  text-align: right;
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.conv-row:hover .conv-time,
.conv-row:focus-within .conv-time {
  visibility: hidden;
}

.conv-actions {
  display: flex;
  align-items: center;
  gap: 1px;
  flex-shrink: 0;
  opacity: 0;
  pointer-events: none;
  width: 0;
  overflow: hidden;
}

.conv-row:hover .conv-actions,
.conv-row:focus-within .conv-actions,
.conv-row.pinned .conv-actions {
  opacity: 1;
  pointer-events: auto;
  width: auto;
  overflow: visible;
}

.conv-action {
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  display: grid;
  place-items: center;
  cursor: pointer;
}

.conv-action:hover,
.conv-action.on {
  color: var(--primary);
  background: var(--code-bg);
}

.conv-action.danger:hover {
  color: var(--danger);
}

.conv-action.on {
  opacity: 1;
}

.show-more {
  width: 100%;
  height: 26px;
  margin-top: 2px;
  padding: 0 10px 0 30px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  font-size: 11px;
  text-align: left;
  cursor: pointer;
}

.show-more:hover {
  background: color-mix(in srgb, var(--text-h) 4%, transparent);
  color: var(--text-secondary);
}
</style>
