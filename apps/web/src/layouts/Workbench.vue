<script setup lang="ts">
import { DockviewVue, type VueComponent } from 'dockview-vue'
import type { DockviewApi, DockviewReadyEvent } from 'dockview-vue'
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, shallowRef, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { panelTitle } from '@/i18n'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import { currentTheme, toggleTheme, type Theme } from '@/theme'
import AgentPanel from '@/panels/AgentPanel.vue'
import SessionSidebar from '@/components/SessionSidebar.vue'
import PanelTab from '@/components/PanelTab.vue'
import ConfirmCard from '@/components/ConfirmCard.vue'
import PortNotifyToast from '@/components/PortNotifyToast.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import { getSidebarCollapsed, setSidebarCollapsed } from '@/utils/layoutPrefs'
import { queueTerminalCwd } from '@/utils/terminalOpen'

const TrajectoryDockPanel = defineAsyncComponent(() => import('@/panels/TrajectoryDockPanel.vue'))
const WorkspacePanel = defineAsyncComponent(() => import('@/panels/WorkspacePanel.vue'))
const ExplorerPanel = defineAsyncComponent(() => import('@/panels/ExplorerPanel.vue'))
const SearchPanel = defineAsyncComponent(() => import('@/panels/SearchPanel.vue'))
const EditorPanel = defineAsyncComponent(() => import('@/panels/EditorPanel.vue'))
const TerminalPanel = defineAsyncComponent(() => import('@/panels/TerminalPanel.vue'))
const ChatListPanel = defineAsyncComponent(() => import('@/panels/ChatListPanel.vue'))
const SkillsPanel = defineAsyncComponent(() => import('@/panels/SkillsPanel.vue'))
const PluginsPanel = defineAsyncComponent(() => import('@/panels/PluginsPanel.vue'))
const ModelsPanel = defineAsyncComponent(() => import('@/panels/ModelsPanel.vue'))
const SettingsPanel = defineAsyncComponent(() => import('@/panels/SettingsPanel.vue'))
const GitPanel = defineAsyncComponent(() => import('@/panels/GitPanel.vue'))
const PortsPanel = defineAsyncComponent(() => import('@/panels/PortsPanel.vue'))
const MemoryPanel = defineAsyncComponent(() => import('@/panels/MemoryPanel.vue'))

const { t } = useI18n()
const store = useAppStore()
const theme = ref<Theme>(currentTheme())
const sidebarCollapsed = ref(getSidebarCollapsed())
const sidebarWidth = ref(260)
const resizing = ref<'sidebar' | null>(null)
const paletteOpen = ref(false)

watch(sidebarCollapsed, (value) => setSidebarCollapsed(value))

const components = {
  workspace: WorkspacePanel,
  explorer: ExplorerPanel,
  search: SearchPanel,
  editor: EditorPanel,
  agent: AgentPanel,
  terminal: TerminalPanel,
  chats: ChatListPanel,
  skills: SkillsPanel,
  plugins: PluginsPanel,
  models: ModelsPanel,
  settings: SettingsPanel,
  git: GitPanel,
  ports: PortsPanel,
  memory: MemoryPanel,
  trajectory: TrajectoryDockPanel,
} as unknown as Record<string, VueComponent>

const dock = shallowRef<DockviewApi | null>(null)

function onTheme(e: Event) {
  theme.value = (e as CustomEvent<Theme>).detail
}

onMounted(() => {
  window.addEventListener('ca-theme', onTheme)
  window.addEventListener('ca-focus-editor', focusEditor)
  window.addEventListener('ca-focus-agent', focusAgent)
  window.addEventListener('ca-open-models', openModels)
  window.addEventListener('ca-open-search', openSearch)
  window.addEventListener('ca-open-explorer', openExplorer)
  window.addEventListener('ca-open-terminal', onOpenTerminal)
  window.addEventListener('ca-open-skills', openSkills)
  window.addEventListener('keydown', onWorkbenchKey)
  window.addEventListener('ca-locale', retitlePanels)
})
onUnmounted(() => {
  window.removeEventListener('ca-theme', onTheme)
  window.removeEventListener('ca-focus-editor', focusEditor)
  window.removeEventListener('ca-focus-agent', focusAgent)
  window.removeEventListener('ca-open-models', openModels)
  window.removeEventListener('ca-open-search', openSearch)
  window.removeEventListener('ca-open-explorer', openExplorer)
  window.removeEventListener('ca-open-terminal', onOpenTerminal)
  window.removeEventListener('ca-open-skills', openSkills)
  window.removeEventListener('keydown', onWorkbenchKey)
  window.removeEventListener('ca-locale', retitlePanels)
  stopResize()
})

function focusEditor() {
  openPanel('editor', 'editor', panelTitle('editor'))
}

function focusAgent() {
  openPanel('agent', 'agent', panelTitle('agent'))
}

function openModels() {
  openPanel('models', 'models', panelTitle('models'))
}

function openSearch() {
  openPanel('search', 'search', panelTitle('search'))
}

function openExplorer() {
  openPanel('explorer', 'explorer', panelTitle('explorer'))
}

function openTerminal() {
  openPanel('terminal', 'terminal', panelTitle('terminal'))
}

async function onOpenTerminal(e: Event) {
  const detail = (e as CustomEvent<{ cwd?: string }>).detail
  queueTerminalCwd(detail?.cwd ?? '')
  openTerminal()
  await nextTick()
  await new Promise<void>((r) => requestAnimationFrame(() => r()))
  window.dispatchEvent(new Event('ca-terminal-cwd'))
}

function openSkills() {
  openPanel('skills', 'skills', panelTitle('skills'))
}

function onWorkbenchKey(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey) || !e.shiftKey || e.key.toLowerCase() !== 'f') return
  if (e.repeat) return
  e.preventDefault()
  store.openSearch()
}

const LAYOUT_SEED = 2

function seed(apiRef: DockviewApi) {
  // Center: Agent + Memory
  apiRef.addPanel({ id: 'agent', component: 'agent', title: panelTitle('agent') })
  apiRef.addPanel({
    id: 'memory',
    component: 'memory',
    title: panelTitle('memory'),
    position: { referencePanel: 'agent', direction: 'within' },
  })

  // Left: Workspace / Explorer / Search
  apiRef.addPanel({
    id: 'workspace',
    component: 'workspace',
    title: panelTitle('workspace'),
    position: { referencePanel: 'agent', direction: 'left' },
  })
  apiRef.addPanel({
    id: 'explorer',
    component: 'explorer',
    title: panelTitle('explorer'),
    position: { referencePanel: 'workspace', direction: 'within' },
  })
  apiRef.addPanel({
    id: 'search',
    component: 'search',
    title: panelTitle('search'),
    position: { referencePanel: 'workspace', direction: 'within' },
  })

  apiRef.getPanel('agent')?.api.setActive()
  store.activity = 'agent'
}

const LEFT_PANELS = ['workspace', 'explorer', 'search'] as const
const CENTER_PANELS = ['agent', 'memory'] as const

function findExisting(apiRef: DockviewApi, ids: readonly string[]) {
  return ids.find((id) => apiRef.getPanel(id))
}

function layoutSeedKey() {
  return `ca.layout.seed.${store.workspaceId || 'default'}`
}

async function onReady(event: DockviewReadyEvent) {
  dock.value = event.api
  let restored = false
  const seedApplied = Number(localStorage.getItem(layoutSeedKey()) || 0) >= LAYOUT_SEED
  try {
    const data = await api<{ layout: unknown }>(`/api/layout?workspace_id=${store.workspaceId}`)
    if (data.layout && seedApplied) {
      event.api.fromJSON(data.layout as never)
      restored = true
    }
  } catch {
    restored = false
  }
  if (!restored) {
    seed(event.api)
    localStorage.setItem(layoutSeedKey(), String(LAYOUT_SEED))
  } else {
    const active = event.api.activePanel
    if (active?.id) store.activity = active.id
  }
  await nextTick()
  requestAnimationFrame(() => {
    window.dispatchEvent(new Event('ca-layout-ready'))
  })
  event.api.onDidLayoutChange(() => {
    const layout = event.api.toJSON()
    api('/api/layout', {
      method: 'PUT',
      body: JSON.stringify({ workspace_id: store.workspaceId, layout }),
    }).catch(() => undefined)
  })
}

function panelPosition(
  apiRef: DockviewApi,
  id: string,
): { referencePanel: string; direction: 'left' | 'right' | 'within' } | undefined {
  if ((LEFT_PANELS as readonly string[]).includes(id)) {
    const left = findExisting(apiRef, LEFT_PANELS)
    if (left) return { referencePanel: left, direction: 'within' }
    const center = findExisting(apiRef, CENTER_PANELS)
    return center ? { referencePanel: center, direction: 'left' } : undefined
  }

  if ((CENTER_PANELS as readonly string[]).includes(id)) {
    const center = findExisting(apiRef, CENTER_PANELS)
    return center ? { referencePanel: center, direction: 'within' } : undefined
  }

  // Everything else opens on the right, tabbed together when possible.
  const rightIds = Object.keys(components).filter(
    (pid) => !(LEFT_PANELS as readonly string[]).includes(pid) && !(CENTER_PANELS as readonly string[]).includes(pid),
  )
  const right = findExisting(apiRef, rightIds)
  if (right) return { referencePanel: right, direction: 'within' }
  const center = findExisting(apiRef, CENTER_PANELS)
  return center ? { referencePanel: center, direction: 'right' } : undefined
}

function retitlePanels() {
  const apiRef = dock.value
  if (!apiRef) return
  for (const panel of apiRef.panels) {
    try {
      panel.api.setTitle(panelTitle(panel.id))
    } catch {
      /* ignore */
    }
  }
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
  const place = panelPosition(apiRef, id)
  apiRef.addPanel({
    id,
    component,
    title,
    ...(place ? { position: place } : {}),
  })
  store.activity = id
}

function onToggleTheme() {
  theme.value = toggleTheme()
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
        @toggle-collapse="sidebarCollapsed = !sidebarCollapsed"
        @open-panel="openPanel"
        @toggle-theme="onToggleTheme"
      />
      <div
        v-if="!sidebarCollapsed"
        class="sidebar-resizer"
        :title="t('workbench.resizeSidebar')"
        @pointerdown="startSidebarResize"
      />
      <div class="workbench-main">
        <div class="dock">
          <DockviewVue
            :class="[dockThemeClass, 'dockview-theme-codeagent']"
            :components="components"
            :default-tab-component="(PanelTab as unknown as VueComponent)"
            @ready="onReady"
          />
        </div>
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
    <CommandPalette
      v-model:open="paletteOpen"
      @open-panel="openPanel"
      @toggle-theme="onToggleTheme"
      @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed"
    />
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
  min-height: 36px;
}
.sidebar-resizer {
  width: 5px;
  flex-shrink: 0;
  cursor: col-resize;
  background: transparent;
  position: relative;
}
.sidebar-resizer::after {
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
.workbench.resizing .sidebar-resizer::after {
  left: 1px;
  width: 3px;
  background: color-mix(in srgb, var(--primary) 55%, var(--border));
}
.workbench.resizing {
  cursor: col-resize;
  user-select: none;
}
</style>
