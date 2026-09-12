<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore, type Conversation, type Workspace } from '@/stores/app'
import { api } from '@/api/http'
import AppIcon from '@/components/AppIcon.vue'
import WorkspaceSwitch from '@/components/WorkspaceSwitch.vue'
import type { WorkspaceSwitchPrefill } from '@/components/WorkspaceSwitch.vue'
import WorkspaceEditDialog from '@/components/WorkspaceEditDialog.vue'
import { useSessionPins } from '@/composables/useSessionPins'
import { useToast } from '@/composables/useToast'
import { formatRelativeTime, formatWorkspaceOpenedAt } from '@/utils/relativeTime'

const PREVIEW_LIMIT = 5

type WorkspaceHostGroup = {
  key: string
  label: string
  kind: 'local' | 'ssh'
  workspaces: Workspace[]
}

const { t } = useI18n()
const toast = useToast()
const store = useAppStore()
const pins = useSessionPins()
const showOpen = ref(false)
const openPrefill = ref<WorkspaceSwitchPrefill | null>(null)
const editingHost = ref<WorkspaceHostGroup | null>(null)
const expandedIds = ref<Set<string>>(new Set())
const showAllIds = ref<Set<string>>(new Set())
const convMap = reactive<Record<string, Conversation[]>>({})
const loading = reactive<Record<string, boolean>>({})
const errors = reactive<Record<string, string>>({})
const openingId = ref<string | null>(null)
const switchingId = ref<string | null>(null)
const creatingId = ref<string | null>(null)
const removingId = ref<string | null>(null)
const editingId = ref<string | null>(null)
const editingTitle = ref('')
const pinTick = ref(0)

const hoverId = ref<string | null>(null)
const hoverHostKey = ref<string | null>(null)
const hoverReady = ref(false)
const tipStyle = ref<Record<string, string>>({})
const tipEl = ref<HTMLElement | null>(null)
let hoverHideTimer = 0
let tipRaf = 0

onMounted(async () => {
  await store.loadWorkspaces()
  if (store.workspaceId) await setExpanded(store.workspaceId, true)
})

onBeforeUnmount(() => {
  clearHoverHide()
  if (tipRaf) cancelAnimationFrame(tipRaf)
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

function isSsh(ws: Workspace) {
  return (ws.kind || 'local') === 'ssh'
}

function hostKey(ws: Workspace) {
  if (!isSsh(ws)) return 'local'
  const host = ws.ssh_host || 'unknown'
  const port = ws.ssh_port || 22
  const user = ws.ssh_user || ''
  return `ssh:${user}@${host}:${port}`
}

function hostEndpoint(ws: Workspace) {
  const host = ws.ssh_host || 'unknown'
  const port = ws.ssh_port || 22
  const user = ws.ssh_user || ''
  return user ? `${user}@${host}:${port}` : `${host}:${port}`
}

function hostLabel(ws: Workspace) {
  if (!isSsh(ws)) return t('workspace.panel.local')
  const custom = (ws.ssh_display_name || '').trim()
  return custom || hostEndpoint(ws)
}

const workspaceGroups = computed<WorkspaceHostGroup[]>(() => {
  const map = new Map<string, WorkspaceHostGroup>()
  for (const ws of store.recentWorkspaces) {
    const key = hostKey(ws)
    let group = map.get(key)
    if (!group) {
      group = {
        key,
        label: hostLabel(ws),
        kind: isSsh(ws) ? 'ssh' : 'local',
        workspaces: [],
      }
      map.set(key, group)
    }
    group.workspaces.push(ws)
    if (isSsh(ws)) {
      const custom = (ws.ssh_display_name || '').trim()
      if (custom) group.label = custom
    }
  }
  // Local first, then SSH hosts alphabetically
  return [...map.values()].sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'local' ? -1 : 1
    return a.label.localeCompare(b.label)
  })
})

const collapsedHosts = ref<Set<string>>(new Set())

function isHostOpen(key: string) {
  return !collapsedHosts.value.has(key)
}

function toggleHost(key: string) {
  const next = new Set(collapsedHosts.value)
  const collapsing = !next.has(key)
  if (collapsing) {
    next.add(key)
    // Collapse sessions under this host when folding the host
    const group = workspaceGroups.value.find((g) => g.key === key)
    if (group?.workspaces.length) {
      const expanded = new Set(expandedIds.value)
      const showAll = new Set(showAllIds.value)
      for (const ws of group.workspaces) {
        expanded.delete(ws.id)
        showAll.delete(ws.id)
      }
      expandedIds.value = expanded
      showAllIds.value = showAll
    }
  } else {
    next.delete(key)
  }
  collapsedHosts.value = next
}

function isHostActive(group: WorkspaceHostGroup) {
  return group.workspaces.some((ws) => ws.id === store.workspaceId)
}

const hoverWorkspace = computed(() =>
  store.recentWorkspaces.find((w) => w.id === hoverId.value) || null,
)

const hoverHost = computed(() =>
  workspaceGroups.value.find((g) => g.key === hoverHostKey.value) || null,
)

function clearHoverHide() {
  if (hoverHideTimer) {
    window.clearTimeout(hoverHideTimer)
    hoverHideTimer = 0
  }
}

function clearTip() {
  hoverId.value = null
  hoverHostKey.value = null
  hoverReady.value = false
}

function placeTip(anchor: DOMRect) {
  const el = tipEl.value
  const width = el?.offsetWidth || 280
  const height = el?.offsetHeight || 120
  const gap = 10
  const margin = 8
  let left = anchor.right + gap
  if (left + width > window.innerWidth - margin) {
    left = Math.max(margin, anchor.left - width - gap)
  }
  let top = anchor.top
  if (top + height > window.innerHeight - margin) {
    top = Math.max(margin, window.innerHeight - height - margin)
  }
  tipStyle.value = {
    position: 'fixed',
    left: `${left}px`,
    top: `${top}px`,
    zIndex: '13000',
  }
  hoverReady.value = true
}

function scheduleTipPlace(anchor: DOMRect, stillValid: () => boolean) {
  hoverReady.value = false
  void nextTick(() => {
    if (tipRaf) cancelAnimationFrame(tipRaf)
    tipRaf = requestAnimationFrame(() => {
      tipRaf = 0
      if (!stillValid()) return
      placeTip(anchor)
    })
  })
}

function showTip(ws: Workspace, e: MouseEvent) {
  clearHoverHide()
  const row = (e.currentTarget as HTMLElement | null)?.closest('.ws-row') as HTMLElement | null
  const anchor = (row || (e.currentTarget as HTMLElement)).getBoundingClientRect()
  hoverHostKey.value = null
  hoverId.value = ws.id
  scheduleTipPlace(anchor, () => hoverId.value === ws.id)
}

function showHostTip(group: WorkspaceHostGroup, e: MouseEvent) {
  clearHoverHide()
  const row = (e.currentTarget as HTMLElement | null)?.closest('.host-row') as HTMLElement | null
  const anchor = (row || (e.currentTarget as HTMLElement)).getBoundingClientRect()
  hoverId.value = null
  hoverHostKey.value = group.key
  scheduleTipPlace(anchor, () => hoverHostKey.value === group.key)
}

function scheduleHideTip() {
  clearHoverHide()
  hoverHideTimer = window.setTimeout(() => {
    clearTip()
    hoverHideTimer = 0
  }, 120)
}

function keepTip() {
  clearHoverHide()
}

function hostSample(group: WorkspaceHostGroup) {
  return group.workspaces[0] || null
}

function hostWorkspaceNames(group: WorkspaceHostGroup) {
  return group.workspaces.map((ws) => ws.name || basename(ws.root_path))
}

function hostLastOpened(group: WorkspaceHostGroup) {
  let best: string | null = null
  for (const ws of group.workspaces) {
    const t = ws.last_opened_at
    if (!t) continue
    if (!best || t > best) best = t
  }
  return best
}

function sessionCountLabel(wsId: string) {
  if (!(wsId in convMap)) return null
  return sortedConvs(wsId).length
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

async function expandAllSessions() {
  // Open all host groups so workspaces underneath are visible
  collapsedHosts.value = new Set()
  // Expand the workspace that owns the current session
  const currentId = store.workspaceId
  if (currentId) await setExpanded(currentId, true)
}

function collapseAllSessions() {
  // Fold every host so workspaces underneath are hidden
  collapsedHosts.value = new Set(workspaceGroups.value.map((g) => g.key))
  expandedIds.value = new Set()
  showAllIds.value = new Set()
}

function toggleShowAll(id: string) {
  const next = new Set(showAllIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  showAllIds.value = next
}

async function loadConvs(wsId: string, force = false) {
  // Reuse cached list on re-expand; current workspace stays in sync via store.conversations watch.
  if (!force && wsId in convMap && !errors[wsId]) return
  if (loading[wsId]) return
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

function startEditHost(group: WorkspaceHostGroup, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (group.kind !== 'ssh') return
  editingHost.value = group
}

function startAddWorkspace(group: WorkspaceHostGroup, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (group.kind === 'ssh') {
    const sample = group.workspaces[0]
    openPrefill.value = {
      mode: 'ssh',
      lockMode: true,
      ssh_display_name: (sample?.ssh_display_name || '').trim() || undefined,
      ssh_host: sample?.ssh_host || '',
      ssh_port: sample?.ssh_port || 22,
      ssh_user: sample?.ssh_user || '',
      reuse_ssh_from: sample?.id,
    }
  } else {
    openPrefill.value = { mode: 'local', lockMode: true }
  }
  showOpen.value = true
}

function closeOpenDialog() {
  showOpen.value = false
  openPrefill.value = null
}

async function removeWorkspace(ws: Workspace, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (removingId.value) return
  const name = ws.name || basename(ws.root_path)
  const ok = await store.askConfirm({
    title: t('workspace.panel.removeTitle'),
    summary: t('workspace.panel.removeSummary', { name }),
    confirmLabel: t('workspace.panel.removeConfirm'),
    danger: true,
  })
  if (!ok) return
  removingId.value = ws.id
  try {
    await store.removeWorkspace(ws.id)
    const next = new Set(expandedIds.value)
    next.delete(ws.id)
    expandedIds.value = next
    delete convMap[ws.id]
    delete loading[ws.id]
    delete errors[ws.id]
  } finally {
    removingId.value = null
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
      try {
        await store.selectWorkspace(ws.id, {
          openExplorer: false,
          conversationId: conv.id,
        })
      } catch (err) {
        // open() may have already flipped workspaceId; still try to open the chat.
        if (store.workspaceId !== ws.id) throw err
      }
    }
    // Always land on the clicked conversation. selectWorkspace restores a preferred
    // id, but a partial failure used to leave the previous workspace's messages up
    // until a second click.
    if (store.workspaceId === ws.id && store.conversationId !== conv.id) {
      await store.openConversation(conv.id)
    }
    window.dispatchEvent(new Event('ca-focus-agent'))
  } catch (err) {
    toast.error(err instanceof Error ? err.message : t('workspace.panel.openFailed'))
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
  let kind: 'approval' | 'queued' | 'running' | null = null
  if (wsId === store.workspaceId && item.id === store.conversationId) {
    if (store.pendingApprovals.length) kind = 'approval'
    else if (store.isRunBusy()) kind = store.runStatus === 'queued' ? 'queued' : 'running'
  } else if (item.awaiting_approval) {
    kind = 'approval'
  } else if (item.active_run_id) {
    if (item.run_status === 'queued') kind = 'queued'
    else if (!item.run_status || item.run_status === 'running') kind = 'running'
  }
  if (!kind) return null
  if (kind === 'approval') {
    return { label: t('workspace.panel.statusApproval'), tone: 'confirm', icon: 'shield' }
  }
  if (kind === 'queued') {
    return { label: t('workspace.panel.statusQueued'), tone: 'queued', icon: 'clock' }
  }
  return { label: t('workspace.panel.statusRunning'), tone: 'running', icon: 'loader' }
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

async function onArchive(wsId: string, conv: Conversation, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  const next = !conv.archived
  if (wsId === store.workspaceId) {
    await store.archiveConversation(conv.id, next)
  } else {
    await api(`/api/conversations/${conv.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ archived: next }),
    })
  }
  if (next) {
    convMap[wsId] = (convMap[wsId] || []).filter((c) => c.id !== conv.id)
  }
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
      <span class="ws-head-title">{{ t('workspace.panel.title') }}</span>
      <div class="ws-head-actions">
        <button
          type="button"
          class="ws-head-btn icon"
          :title="t('workspace.panel.collapseHosts')"
          :disabled="!store.recentWorkspaces.length || collapsedHosts.size >= workspaceGroups.length"
          @click="collapseAllSessions"
        >
          <AppIcon name="collapse-all" :size="14" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ws-head-btn icon"
          :title="t('workspace.panel.expandHosts')"
          :disabled="!store.recentWorkspaces.length"
          @click="expandAllSessions"
        >
          <AppIcon name="expand-all" :size="14" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ws-head-btn"
          :title="t('workspace.panel.openWorkspace')"
          @click="openPrefill = null; showOpen = true"
        >
          <AppIcon name="plus" :size="14" :stroke-width="1.75" />
          <span>{{ t('workspace.panel.open') }}</span>
        </button>
      </div>
    </header>

    <div class="workspace-body">
      <p v-if="!store.recentWorkspaces.length" class="empty">{{ t('workspace.panel.empty') }}</p>

      <div
        v-for="group in workspaceGroups"
        :key="group.key"
        class="host-block"
        :class="{ current: isHostActive(group) }"
      >
        <div
          class="host-row"
          @mouseenter="showHostTip(group, $event)"
          @mouseleave="scheduleHideTip"
        >
          <button type="button" class="host-main" @click="toggleHost(group.key)">
            <AppIcon
              class="host-chev"
              :name="isHostOpen(group.key) ? 'chevron-down' : 'chevron-right'"
              :size="11"
              :stroke-width="2"
            />
            <AppIcon
              class="host-icon"
              :class="{ 'is-ssh': group.kind === 'ssh' }"
              :name="group.kind === 'ssh' ? 'globe' : 'folder'"
              :size="13"
              :stroke-width="1.75"
            />
            <span class="host-label">{{ group.label }}</span>
            <span v-if="group.kind === 'ssh'" class="host-ssh-mark" title="SSH">SSH</span>
          </button>
          <div class="host-end">
            <span class="host-count">{{ group.workspaces.length }}</span>
            <div class="host-tools">
              <button
                v-if="group.kind === 'ssh'"
                type="button"
                class="host-tool"
                :title="t('workspace.panel.editHost')"
                @click="startEditHost(group, $event)"
              >
                <AppIcon name="pencil" :size="13" :stroke-width="1.75" />
              </button>
              <button
                type="button"
                class="host-tool"
                :title="group.kind === 'ssh' ? t('workspace.panel.addRemoteWorkspace') : t('workspace.panel.addLocalWorkspace')"
                @click="startAddWorkspace(group, $event)"
              >
                <AppIcon name="plus" :size="13" :stroke-width="1.75" />
              </button>
            </div>
            <span v-if="isHostActive(group)" class="host-dot" :title="t('workspace.panel.currentHost')" />
          </div>
        </div>

        <ul v-if="isHostOpen(group.key)" class="ws-list">
          <li
            v-for="ws in group.workspaces"
            :key="ws.id"
            class="ws-group"
            :class="{ current: ws.id === store.workspaceId, open: isExpanded(ws.id) }"
          >
            <div
              class="ws-row"
              @mouseenter="showTip(ws, $event)"
              @mouseleave="scheduleHideTip"
            >
              <button type="button" class="ws-main" @click="toggleExpand(ws.id)">
                <AppIcon
                  class="ws-chev"
                  :name="isExpanded(ws.id) ? 'chevron-down' : 'chevron-right'"
                  :size="12"
                  :stroke-width="2"
                />
                <AppIcon class="ws-icon" name="folder" :size="14" :stroke-width="1.75" />
                <span class="ws-copy">
                  <span class="ws-name">{{ ws.name || basename(ws.root_path) }}</span>
                  <span
                    v-if="ws.id === store.workspaceId && store.workspaceRootMissing"
                    class="ws-missing-badge"
                  >{{ t('workspace.panel.rootMissingBadge') }}</span>
                </span>
              </button>
              <div class="ws-end">
                <div class="ws-tools">
                  <button
                    type="button"
                    class="ws-tool"
                    :title="t('workspace.panel.newSession')"
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
                    {{ t('workspace.panel.open') }}
                  </button>
                  <button
                    type="button"
                    class="ws-tool danger"
                    :title="t('workspace.panel.removeWorkspace')"
                    :disabled="removingId === ws.id"
                    @click="removeWorkspace(ws, $event)"
                  >
                    <AppIcon name="trash" :size="13" :stroke-width="1.75" />
                  </button>
                </div>
                <span v-if="ws.id === store.workspaceId" class="ws-dot" :title="t('workspace.panel.currentWorkspace')" />
              </div>
            </div>

            <div v-if="isExpanded(ws.id)" class="ws-sessions">
              <p v-if="loading[ws.id]" class="hint">{{ t('workspace.panel.loading') }}</p>
              <p v-else-if="errors[ws.id]" class="hint err">
                <span>{{ errors[ws.id] }}</span>
                <button type="button" class="hint-retry" @click="loadConvs(ws.id, true)">
                  {{ t('workspace.panel.retry') }}
                </button>
              </p>
              <p v-else-if="!sortedConvs(ws.id).length" class="hint">{{ t('workspace.panel.noSessions') }}</p>

              <div
                v-for="conv in visibleConvs(ws.id)"
                :key="conv.id"
                class="conv-row"
                :class="{
                  active: conv.id === store.conversationId && ws.id === store.workspaceId,
                  pinned: pins.isPinnedIn(ws.id, conv.id),
                  opening: openingId === conv.id,
                }"
                :aria-busy="openingId === conv.id"
                @click="openConv(ws, conv)"
              >
                <span class="conv-status-slot">
                  <span
                    v-if="openingId === conv.id"
                    class="conv-status opening"
                    :title="t('workspace.panel.opening')"
                    :aria-label="t('workspace.panel.opening')"
                  >
                    <AppIcon class="spin" name="loader" :size="12" :stroke-width="1.75" />
                  </span>
                  <template v-else v-for="st in [statusByKey.get(`${ws.id}:${conv.id}`)]" :key="`${conv.id}-status`">
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
                    :aria-label="t('workspace.panel.rename')"
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
                  <button type="button" class="conv-action" :title="t('workspace.panel.rename')" @click="startRename(conv, $event)">
                    <AppIcon name="pencil" :size="13" :stroke-width="1.75" />
                  </button>
                  <button
                    type="button"
                    class="conv-action"
                    :class="{ on: pins.isPinnedIn(ws.id, conv.id) }"
                    :title="pins.isPinnedIn(ws.id, conv.id) ? t('workspace.panel.unpin') : t('workspace.panel.pin')"
                    @click="onTogglePin(ws.id, conv.id, $event)"
                  >
                    <AppIcon name="pin" :size="13" :stroke-width="1.75" />
                  </button>
                  <button
                    type="button"
                    class="conv-action"
                    :title="conv.archived ? t('workspace.panel.unarchive') : t('workspace.panel.archive')"
                    @click="onArchive(ws.id, conv, $event)"
                  >
                    <AppIcon name="inbox" :size="13" :stroke-width="1.75" />
                  </button>
                  <button type="button" class="conv-action danger" :title="t('workspace.panel.deleteSession')" @click="onDelete(ws.id, conv.id, $event)">
                    <AppIcon name="trash" :size="13" :stroke-width="1.75" />
                  </button>
                </span>

                <span class="conv-turns">{{ t('workspace.panel.turns', { n: turnCount(ws.id, conv) }) }}</span>
              </div>

              <button
                v-if="hiddenCount(ws.id)"
                type="button"
                class="show-more"
                @click="toggleShowAll(ws.id)"
              >
                {{ t('workspace.panel.showMore', { n: hiddenCount(ws.id) }) }}
              </button>
              <button
                v-else-if="showsAll(ws.id) && sortedConvs(ws.id).length > PREVIEW_LIMIT"
                type="button"
                class="show-more"
                @click="toggleShowAll(ws.id)"
              >
                {{ t('workspace.panel.showLess') }}
              </button>
            </div>
          </li>
        </ul>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="hoverHost || hoverWorkspace"
        ref="tipEl"
        class="ws-tip"
        :class="{ ready: hoverReady }"
        :style="tipStyle"
        role="tooltip"
        @mouseenter="keepTip"
        @mouseleave="scheduleHideTip"
      >
        <template v-if="hoverHost">
          <div class="ws-tip-head">
            <AppIcon
              class="ws-tip-icon"
              :class="{ 'is-ssh': hoverHost.kind === 'ssh' }"
              :name="hoverHost.kind === 'ssh' ? 'globe' : 'folder'"
              :size="15"
              :stroke-width="1.75"
            />
            <div class="ws-tip-titles">
              <strong>{{ hoverHost.label }}</strong>
              <span class="ws-tip-badge" :class="hoverHost.kind === 'ssh' ? 'remote' : 'local'">
                {{ hoverHost.kind === 'ssh' ? t('workspace.panel.remote') : t('workspace.panel.local') }}
              </span>
              <span v-if="isHostActive(hoverHost)" class="ws-tip-badge">{{ t('workspace.panel.current') }}</span>
            </div>
          </div>
          <dl class="ws-tip-meta">
            <div v-if="hoverHost.kind === 'ssh' && hostSample(hoverHost)">
              <dt>{{ t('workspace.panel.host') }}</dt>
              <dd class="mono">{{ hostEndpoint(hostSample(hoverHost)!) }}</dd>
            </div>
            <div>
              <dt>{{ t('workspace.panel.workspaces') }}</dt>
              <dd>{{ t('workspace.panel.count', { n: hoverHost.workspaces.length }) }}</dd>
            </div>
            <div v-if="hostWorkspaceNames(hoverHost).length">
              <dt>{{ t('workspace.panel.dirs') }}</dt>
              <dd class="ws-tip-list" :title="hostWorkspaceNames(hoverHost).join('\n')">
                {{ hostWorkspaceNames(hoverHost).slice(0, 6).join('、') }}
                <template v-if="hostWorkspaceNames(hoverHost).length > 6">
                  {{ t('workspace.panel.dirsMore', { n: hostWorkspaceNames(hoverHost).length }) }}
                </template>
              </dd>
            </div>
            <div v-if="hostLastOpened(hoverHost)">
              <dt>{{ t('workspace.panel.lastOpened') }}</dt>
              <dd>{{ formatWorkspaceOpenedAt(hostLastOpened(hoverHost)!) }}</dd>
            </div>
          </dl>
        </template>
        <template v-else-if="hoverWorkspace">
          <div class="ws-tip-head">
            <AppIcon
              class="ws-tip-icon"
              :name="isSsh(hoverWorkspace) ? 'globe' : 'folder'"
              :size="15"
              :stroke-width="1.75"
            />
            <div class="ws-tip-titles">
              <strong>{{ hoverWorkspace.name || basename(hoverWorkspace.root_path) }}</strong>
              <span v-if="isSsh(hoverWorkspace)" class="ws-tip-badge remote">{{ t('workspace.panel.remote') }}</span>
              <span v-if="hoverWorkspace.id === store.workspaceId" class="ws-tip-badge">{{ t('workspace.panel.current') }}</span>
            </div>
          </div>
          <dl class="ws-tip-meta">
            <div v-if="isSsh(hoverWorkspace)">
              <dt>{{ t('workspace.panel.host') }}</dt>
              <dd class="mono">{{ hostEndpoint(hoverWorkspace) }}</dd>
            </div>
            <div>
              <dt>{{ t('workspace.panel.path') }}</dt>
              <dd class="mono" :title="hoverWorkspace.display_path || hoverWorkspace.root_path">
                {{ hoverWorkspace.display_path || hoverWorkspace.root_path }}
              </dd>
            </div>
            <div v-if="hoverWorkspace.last_opened_at">
              <dt>{{ t('workspace.panel.lastOpened') }}</dt>
              <dd>{{ formatWorkspaceOpenedAt(hoverWorkspace.last_opened_at) }}</dd>
            </div>
            <div v-if="hoverWorkspace.created_at">
              <dt>{{ t('workspace.panel.created') }}</dt>
              <dd>{{ formatRelativeTime(hoverWorkspace.created_at) }}</dd>
            </div>
            <div v-if="sessionCountLabel(hoverWorkspace.id) != null">
              <dt>{{ t('workspace.panel.sessions') }}</dt>
              <dd>{{ t('workspace.panel.count', { n: sessionCountLabel(hoverWorkspace.id) }) }}</dd>
            </div>
          </dl>
        </template>
      </div>
    </Teleport>

    <WorkspaceSwitch
      v-if="showOpen"
      :prefill="openPrefill"
      @close="closeOpenDialog"
    />
    <WorkspaceEditDialog
      v-if="editingHost"
      :workspaces="editingHost.workspaces"
      :label="editingHost.label"
      @close="editingHost = null"
    />
  </div>
</template>

<style scoped>
.workspace-panel {
  background: var(--sidebar-bg);
}

.ws-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 4px 8px;
  flex-shrink: 0;
}

.ws-head-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.ws-head-actions {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.ws-head-btn {
  height: 22px;
  padding: 0 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.ws-head-btn.icon {
  width: 22px;
  min-width: 22px;
  padding: 0;
  justify-content: center;
}

.ws-head-btn:hover:not(:disabled) {
  background: var(--code-bg);
  color: var(--text-h);
}

.ws-head-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.ws-missing-badge {
  display: inline-flex;
  align-items: center;
  margin-left: 6px;
  padding: 0 5px;
  height: 16px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--danger, #ef4444);
  background: color-mix(in srgb, var(--danger, #ef4444) 14%, transparent);
  vertical-align: middle;
  flex-shrink: 0;
}

.workspace-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px 8px 12px;
}

.host-block {
  margin-bottom: 10px;
  padding: 4px 0 6px;
  border: var(--border-width) solid var(--border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--text-h) 3%, var(--sidebar-bg));
  overflow: hidden;
}

.host-block.current {
  border-color: color-mix(in srgb, #22c55e 35%, var(--border));
  background: color-mix(in srgb, #22c55e 6%, var(--sidebar-bg));
}

.host-row {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 30px;
  margin: 0 4px;
  padding-right: 4px;
  border-radius: 8px;
  color: var(--text-secondary);
}

.host-row:hover {
  background: color-mix(in srgb, var(--text-h) 5%, transparent);
  color: var(--text-h);
}

.host-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 4px 6px 4px 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.host-tools {
  position: absolute;
  right: 100%;
  top: 50%;
  display: flex;
  align-items: center;
  gap: 0;
  margin-right: 2px;
  padding: 1px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--panel-bg) 88%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--border) 80%, transparent);
  opacity: 0;
  pointer-events: none;
  transform: translate(4px, -50%);
  transition: opacity 0.12s ease, transform 0.12s ease;
}

.host-end {
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  min-height: 22px;
  min-width: 22px;
  justify-content: flex-end;
}

.host-row:hover .host-tools,
.host-row:focus-within .host-tools {
  opacity: 1;
  pointer-events: auto;
  transform: translate(0, -50%);
}

.host-row:hover .host-count,
.host-row:focus-within .host-count {
  opacity: 1;
}

@media (hover: none) {
  .host-tools {
    position: static;
    opacity: 1;
    pointer-events: auto;
    transform: none;
    margin-right: 0;
    background: transparent;
    box-shadow: none;
    padding: 0;
  }
}

.host-tool {
  box-sizing: border-box;
  width: 22px;
  height: 22px;
  min-width: 22px;
  padding: 0;
  margin: 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
  flex-shrink: 0;
  cursor: pointer;
}

.host-tool :deep(.app-icon) {
  display: block;
}

.host-tool:hover {
  background: var(--code-bg);
  color: var(--text-h);
}

.host-chev,
.host-icon {
  flex-shrink: 0;
  opacity: 0.95;
  color: var(--text-h);
}

.host-block.current .host-icon {
  color: #16a34a;
}

.host-icon.is-ssh {
  color: #0284c7;
}

.host-block.current .host-icon.is-ssh {
  color: #0284c7;
}

.host-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.01em;
  color: var(--text-h);
}

.host-ssh-mark {
  flex-shrink: 0;
  height: 15px;
  padding: 0 4px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 15px;
  color: #0284c7;
  background: color-mix(in srgb, #0284c7 14%, transparent);
}

.ws-badge {
  flex-shrink: 0;
  height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
  letter-spacing: 0.02em;
}

.ws-badge.remote,
.ws-tip-badge.remote {
  background: color-mix(in srgb, var(--primary) 16%, transparent);
  color: var(--primary);
}

.ws-tip-badge.local {
  background: color-mix(in srgb, var(--text-muted) 16%, transparent);
  color: var(--text-secondary);
}

.host-count {
  flex-shrink: 0;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--text-h) 8%, transparent);
  font-variant-numeric: tabular-nums;
  opacity: 0.55;
  transition: opacity 0.12s ease;
}

.host-dot {
  width: 6px;
  height: 6px;
  margin: 0 8px 0 4px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 2px color-mix(in srgb, #22c55e 25%, transparent);
  flex-shrink: 0;
}

.host-block .ws-list {
  padding: 2px 4px 2px 6px;
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
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.hint-retry {
  border: 0;
  border-radius: 5px;
  padding: 2px 8px;
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  color: var(--primary);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.hint-retry:hover {
  background: color-mix(in srgb, var(--primary) 18%, transparent);
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

.ws-row:hover {
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

.ws-icon {
  flex-shrink: 0;
  color: var(--text-secondary);
}

.ws-group.current .ws-icon {
  color: var(--primary);
}

.ws-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0;
}

.ws-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
  line-height: 17px;
  min-width: 0;
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

.ws-tool.danger:hover {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 8%, transparent);
}

.ws-tool:disabled {
  opacity: 0.45;
  cursor: default;
}

.ws-sessions {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 1px 0 6px 8px;
}

.conv-row {
  position: relative;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 4px 8px;
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

.conv-row.opening {
  opacity: 0.78;
  pointer-events: none;
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

.conv-status.running,
.conv-status.opening {
  color: var(--primary);
}

.conv-status.running :deep(svg),
.conv-status.opening :deep(svg),
.spin {
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
  align-self: center;
  gap: 8px;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  line-height: 22px;
  height: 22px;
}

.conv-turns {
  flex-shrink: 0;
  align-self: center;
  min-width: 2.5rem;
  height: 22px;
  line-height: 22px;
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
  display: inline-flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  gap: 1px;
  flex-shrink: 0;
  height: 22px;
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
  box-sizing: border-box;
  width: 22px;
  height: 22px;
  min-width: 22px;
  padding: 0;
  margin: 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
  flex-shrink: 0;
  cursor: pointer;
}

.conv-action :deep(.app-icon) {
  display: block;
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
  padding: 0 10px 0 8px;
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

<style scoped>
.ws-tip {
  width: min(320px, calc(100vw - 16px));
  padding: 10px 12px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: var(--dropdown-shadow);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}
.ws-tip.ready {
  opacity: 1;
  pointer-events: auto;
}
html[data-theme='dark'] .ws-tip {
  box-shadow: var(--dropdown-shadow-dark);
}
.ws-tip-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}
.ws-tip-icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--primary);
}
.ws-tip-icon.is-ssh {
  color: #0284c7;
}
.ws-tip-list {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: normal;
  line-height: 1.4;
}
.ws-tip-titles {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.ws-tip-titles strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
}
.ws-tip-badge {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 10px;
  font-weight: 600;
}
.ws-tip-badge.local {
  background: color-mix(in srgb, var(--text-muted) 16%, transparent);
  color: var(--text-secondary);
}
.ws-tip-badge.remote {
  background: color-mix(in srgb, var(--primary) 16%, transparent);
  color: var(--primary);
}
.ws-tip-meta {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ws-tip-meta > div {
  display: grid;
  grid-template-columns: 4.5em minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}
.ws-tip-meta dt {
  margin: 0;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  line-height: 1.45;
}
.ws-tip-meta dd {
  margin: 0;
  font-size: 12px;
  color: var(--text);
  line-height: 1.45;
  word-break: break-all;
}
.ws-tip-meta dd.mono {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-secondary);
}
</style>
