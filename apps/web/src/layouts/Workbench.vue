<script setup lang="ts">
import { DockviewVue } from 'dockview-vue'
import type { DockviewApi, DockviewReadyEvent } from 'dockview-vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import { currentTheme, toggleTheme, type Theme } from '@/theme'
import SessionSidebar from '@/components/SessionSidebar.vue'
import PanelTab from '@/components/PanelTab.vue'
import TrajectoryPanel from '@/panels/TrajectoryPanel.vue'
import TrajectoryDockPanel from '@/panels/TrajectoryDockPanel.vue'
import WorkspacePanel from '@/panels/WorkspacePanel.vue'
import ExplorerPanel from '@/panels/ExplorerPanel.vue'
import EditorPanel from '@/panels/EditorPanel.vue'
import AgentPanel from '@/panels/AgentPanel.vue'
import TerminalPanel from '@/panels/TerminalPanel.vue'
import ChatListPanel from '@/panels/ChatListPanel.vue'
import SkillsPanel from '@/panels/SkillsPanel.vue'
import ModelsPanel from '@/panels/ModelsPanel.vue'
import SettingsPanel from '@/panels/SettingsPanel.vue'
import ConfirmCard from '@/components/ConfirmCard.vue'
import PortNotifyToast from '@/components/PortNotifyToast.vue'
import GitPanel from '@/panels/GitPanel.vue'
import PortsPanel from '@/panels/PortsPanel.vue'
import { getSidebarCollapsed, getTrajectoryOpen, setSidebarCollapsed, setTrajectoryOpen } from '@/utils/layoutPrefs'

const store = useAppStore()
const theme = ref<Theme>(currentTheme())
const sidebarCollapsed = ref(getSidebarCollapsed())
const sidebarWidth = ref(260)
const trajectoryOpen = ref(getTrajectoryOpen())
const trajectoryWidth = ref(340)
const resizing = ref<'sidebar' | 'trajectory' | null>(null)

watch(sidebarCollapsed, (value) => setSidebarCollapsed(value))
watch(trajectoryOpen, (value) => setTrajectoryOpen(value))

const components = {
  workspace: WorkspacePanel,
  explorer: ExplorerPanel,
  editor: EditorPanel,
  agent: AgentPanel,
  terminal: TerminalPanel,
  chats: ChatListPanel,
  skills: SkillsPanel,
  models: ModelsPanel,
  settings: SettingsPanel,
  git: GitPanel,
  ports: PortsPanel,
  trajectory: TrajectoryDockPanel,
}

const dock = ref<DockviewApi | null>(null)

function onTheme(e: Event) {
  theme.value = (e as CustomEvent<Theme>).detail
}

onMounted(() => {
  window.addEventListener('ca-theme', onTheme)
  window.addEventListener('ca-focus-editor', focusEditor)
  window.addEventListener('ca-focus-agent', focusAgent)
})
onUnmounted(() => {
  window.removeEventListener('ca-theme', onTheme)
  window.removeEventListener('ca-focus-editor', focusEditor)
  window.removeEventListener('ca-focus-agent', focusAgent)
  stopResize()
})

function focusEditor() {
  openPanel('editor', 'editor', '编辑器')
}

function focusAgent() {
  openPanel('agent', 'agent', 'Agent')
}

function seed(apiRef: DockviewApi) {
  apiRef.addPanel({ id: 'agent', component: 'agent', title: 'Agent' })
  store.activity = 'agent'
}

async function onReady(event: DockviewReadyEvent) {
  dock.value = event.api
  let restored = false
  try {
    const data = await api<{ layout: unknown }>(`/api/layout?workspace_id=${store.workspaceId}`)
    if (data.layout) {
      event.api.fromJSON(data.layout as never)
      restored = true
    }
  } catch {
    restored = false
  }
  if (!restored) seed(event.api)
  event.api.onDidLayoutChange(() => {
    const layout = event.api.toJSON()
    api('/api/layout', {
      method: 'PUT',
      body: JSON.stringify({ workspace_id: store.workspaceId, layout }),
    }).catch(() => undefined)
  })
}

const placements: Record<string, { referencePanel: string; direction: 'left' | 'right' | 'below' }> = {
  workspace: { referencePanel: 'agent', direction: 'left' },
  explorer: { referencePanel: 'agent', direction: 'left' },
  editor: { referencePanel: 'agent', direction: 'left' },
  terminal: { referencePanel: 'agent', direction: 'below' },
  agent: { referencePanel: 'agent', direction: 'right' },
  chats: { referencePanel: 'agent', direction: 'left' },
  git: { referencePanel: 'agent', direction: 'left' },
  ports: { referencePanel: 'agent', direction: 'below' },
  skills: { referencePanel: 'agent', direction: 'right' },
  models: { referencePanel: 'agent', direction: 'right' },
  settings: { referencePanel: 'agent', direction: 'right' },
  trajectory: { referencePanel: 'agent', direction: 'right' },
}

function openPanel(id: string, component: string, title: string) {
  const apiRef = dock.value
  if (!apiRef) return
  const existing = apiRef.getPanel(id)
  if (existing) {
    if (!existing.api.group.api.isVisible) existing.api.group.api.setVisible(true)
    existing.api.setActive()
    store.activity = id
    return
  }
  const place = placements[id]
  const refId = place && apiRef.getPanel(place.referencePanel) ? place.referencePanel : undefined
  apiRef.addPanel({
    id,
    component,
    title,
    ...(refId ? { position: { referencePanel: refId, direction: place.direction } } : {}),
  })
  store.activity = id
}

function onToggleTheme() {
  theme.value = toggleTheme()
}

function toggleTrajectory() {
  trajectoryOpen.value = !trajectoryOpen.value
}

function popoutTrajectory() {
  openPanel('trajectory', 'trajectory', '轨迹')
  trajectoryOpen.value = false
}

function openTrajectoryDock() {
  openPanel('trajectory', 'trajectory', '轨迹')
}

function startSidebarResize(e: PointerEvent) {
  if (sidebarCollapsed.value) return
  resizing.value = 'sidebar'
  const startX = e.clientX
  const startWidth = sidebarWidth.value
  const onMove = (ev: PointerEvent) => {
    sidebarWidth.value = Math.min(420, Math.max(200, startWidth + ev.clientX - startX))
  }
  const onUp = () => stopResize(onMove, onUp)
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
}

function startTrajectoryResize(e: PointerEvent) {
  resizing.value = 'trajectory'
  const startX = e.clientX
  const startWidth = trajectoryWidth.value
  const onMove = (ev: PointerEvent) => {
    const delta = startX - ev.clientX
    trajectoryWidth.value = Math.min(560, Math.max(280, startWidth + delta))
  }
  const onUp = () => stopResize(onMove, onUp)
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
}

function stopResize(onMove?: (ev: PointerEvent) => void, onUp?: () => void) {
  resizing.value = null
  if (onMove) window.removeEventListener('pointermove', onMove)
  if (onUp) window.removeEventListener('pointerup', onUp)
}

const sidebarStyle = computed(() =>
  sidebarCollapsed.value ? { width: 'var(--sidebar-rail-w)' } : { width: `${sidebarWidth.value}px` },
)

const dockThemeClass = computed(() =>
  theme.value === 'dark' ? 'dockview-theme-dark' : 'dockview-theme-light',
)
</script>

<template>
  <div class="workbench" :class="{ resizing: !!resizing }">
    <div class="workbench-body">
      <SessionSidebar
        :style="sidebarStyle"
        :collapsed="sidebarCollapsed"
        :theme="theme"
        :trajectory-open="trajectoryOpen"
        @toggle-collapse="sidebarCollapsed = !sidebarCollapsed"
        @open-panel="openPanel"
        @toggle-theme="onToggleTheme"
        @toggle-trajectory="toggleTrajectory"
        @open-trajectory-dock="openTrajectoryDock"
      />
      <div
        v-if="!sidebarCollapsed"
        class="sidebar-resizer"
        title="拖拽调整侧栏宽度"
        @pointerdown="startSidebarResize"
      />
      <div class="workbench-main">
        <div class="dock">
          <DockviewVue
            :class="[dockThemeClass, 'dockview-theme-codeagent']"
            :components="components"
            :default-tab-component="PanelTab"
            @ready="onReady"
          />
        </div>
        <div
          v-if="trajectoryOpen"
          class="details-resizer"
          title="拖拽调整轨迹面板宽度"
          @pointerdown="startTrajectoryResize"
        />
        <TrajectoryPanel
          v-if="trajectoryOpen"
          mode="sidebar"
          :style="{ width: `${trajectoryWidth}px`, flexShrink: 0 }"
          @close="trajectoryOpen = false"
          @popout="popoutTrajectory"
        />
      </div>
    </div>
    <ConfirmCard
      v-if="store.confirmDialog"
      :title="store.confirmDialog.title"
      :summary="store.confirmDialog.summary"
      :details="store.confirmDialog.details"
      :confirm-label="store.confirmDialog.confirmLabel"
      :cancel-label="store.confirmDialog.cancelLabel"
      :danger="store.confirmDialog.danger !== false"
      @confirm="store.closeConfirm(true)"
      @cancel="store.closeConfirm(false)"
    />
    <PortNotifyToast />
  </div>
</template>

<style scoped>
.workbench {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--page-bg);
}
.workbench-body {
  flex: 1;
  min-height: 0;
  display: flex;
}
.workbench-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
}
.dock {
  flex: 1;
  min-width: 0;
  min-height: 0;
}
.dock :deep(.dockview-theme-codeagent),
.dock :deep(.dv-dockview) {
  height: 100%;
}
.dock :deep(.dv-tabs-and-actions-container) {
  min-height: 34px;
  padding-top: 2px;
}
.sidebar-resizer,
.details-resizer {
  width: 5px;
  flex-shrink: 0;
  cursor: col-resize;
  background: transparent;
  position: relative;
}
.sidebar-resizer::after,
.details-resizer::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 2px;
  width: 1px;
  background: var(--border);
  transition: background 0.15s ease, width 0.15s ease, left 0.15s ease;
}
.sidebar-resizer:hover::after,
.details-resizer:hover::after,
.workbench.resizing .sidebar-resizer::after,
.workbench.resizing .details-resizer::after {
  left: 1px;
  width: 3px;
  background: color-mix(in srgb, var(--primary) 55%, var(--border));
}
.workbench.resizing {
  cursor: col-resize;
  user-select: none;
}
</style>
