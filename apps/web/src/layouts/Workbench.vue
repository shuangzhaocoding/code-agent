<script setup lang="ts">
import { DockviewVue, type VueComponent } from 'dockview-vue'
import type { DockviewApi, DockviewReadyEvent } from 'dockview-vue'
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, shallowRef, ref } from 'vue'
import { panelTitle } from '@/i18n'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import { currentTheme, toggleTheme, type Theme } from '@/theme'
import AgentPanel from '@/panels/AgentPanel.vue'
import TopMenuBar from '@/components/TopMenuBar.vue'
import DesktopTitleBar from '@/components/DesktopTitleBar.vue'
import PanelTab from '@/components/PanelTab.vue'
import ConfirmCard from '@/components/ConfirmCard.vue'
import PortNotifyToast from '@/components/PortNotifyToast.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import AppToastHost from '@/components/AppToastHost.vue'
import {
  applyLayoutPreset,
  clearDock,
  DEFAULT_LAYOUT_PRESET,
  getStoredLayoutPreset,
  isLayoutPresetId,
  setStoredLayoutPreset,
  type LayoutPresetId,
} from '@/utils/layoutPresets'
import { getMenuBarPosition, isMenuBarPosition, type MenuBarPosition } from '@/utils/layoutPrefs'
import { hasCustomTitleBar } from '@/utils/desktop'
import { queueTerminalCwd, queueTerminalRun } from '@/utils/terminalOpen'
import type { TerminalRunRequest } from '@/utils/scriptRun'
import { chatExternalHref, isHttpUrl, openExternalUrl, preferInAppPreview } from '@/utils/openUrl'
import { openUrlPreview } from '@/composables/useUrlPreview'

const TrajectoryDockPanel = defineAsyncComponent(() => import('@/panels/TrajectoryDockPanel.vue'))
const WorkspacePanel = defineAsyncComponent(() => import('@/panels/WorkspacePanel.vue'))
const ExplorerPanel = defineAsyncComponent(() => import('@/panels/ExplorerPanel.vue'))
const SearchPanel = defineAsyncComponent(() => import('@/panels/SearchPanel.vue'))
const EditorPanel = defineAsyncComponent(() => import('@/panels/EditorPanel.vue'))
const TerminalPanel = defineAsyncComponent(() => import('@/panels/TerminalPanel.vue'))
const SkillsPanel = defineAsyncComponent(() => import('@/panels/SkillsPanel.vue'))
const PluginsPanel = defineAsyncComponent(() => import('@/panels/PluginsPanel.vue'))
const ModelsPanel = defineAsyncComponent(() => import('@/panels/ModelsPanel.vue'))
const SettingsPanel = defineAsyncComponent(() => import('@/panels/SettingsPanel.vue'))
const GitPanel = defineAsyncComponent(() => import('@/panels/GitPanel.vue'))
const PortsPanel = defineAsyncComponent(() => import('@/panels/PortsPanel.vue'))
const UrlPreviewPanel = defineAsyncComponent(() => import('@/panels/UrlPreviewPanel.vue'))
const MemoryPanel = defineAsyncComponent(() => import('@/panels/MemoryPanel.vue'))

const store = useAppStore()
const theme = ref<Theme>(currentTheme())
const menuPosition = ref<MenuBarPosition>(getMenuBarPosition())
const paletteOpen = ref(false)
const paletteMode = ref<'commands' | 'files'>('commands')
const customTitleBar = hasCustomTitleBar()
const menuAsTitleBar = computed(() => customTitleBar && menuPosition.value === 'top')
const showDesktopStrip = computed(() => customTitleBar && menuPosition.value !== 'top')

const components = {
  workspace: WorkspacePanel,
  explorer: ExplorerPanel,
  search: SearchPanel,
  editor: EditorPanel,
  agent: AgentPanel,
  terminal: TerminalPanel,
  skills: SkillsPanel,
  plugins: PluginsPanel,
  models: ModelsPanel,
  settings: SettingsPanel,
  git: GitPanel,
  ports: PortsPanel,
  preview: UrlPreviewPanel,
  memory: MemoryPanel,
  trajectory: TrajectoryDockPanel,
} as unknown as Record<string, VueComponent>

const dock = shallowRef<DockviewApi | null>(null)

function onTheme(e: Event) {
  theme.value = (e as CustomEvent<Theme>).detail
}

function onMenuPosition(e: Event) {
  const position = (e as CustomEvent<{ position: MenuBarPosition }>).detail?.position
  if (isMenuBarPosition(position)) menuPosition.value = position
}

function onChatUrlClick(e: MouseEvent) {
  if (e.defaultPrevented) return
  if (e.button !== 0 && e.button !== 1) return
  const url = chatExternalHref(e.target)
  if (!url) return
  const el = e.target instanceof Element ? e.target : null
  if (!el?.closest('.markdown-body, .markdown-inline, .think-body, .user-text, .user-files')) return
  e.preventDefault()
  e.stopPropagation()
  const openInApp = preferInAppPreview(e)
  if (openInApp && isHttpUrl(url)) {
    openUrlPreview(url)
    return
  }
  void openExternalUrl(url)
}

onMounted(() => {
  window.addEventListener('click', onChatUrlClick, true)
  window.addEventListener('auxclick', onChatUrlClick, true)
  window.addEventListener('ca-theme', onTheme)
  window.addEventListener('ca-menu-position', onMenuPosition as EventListener)
  window.addEventListener('ca-focus-editor', focusEditor)
  window.addEventListener('ca-focus-agent', focusAgent)
  window.addEventListener('ca-open-models', openModels)
  window.addEventListener('ca-open-search', openSearch)
  window.addEventListener('ca-open-explorer', openExplorer)
  window.addEventListener('ca-open-terminal', onOpenTerminal)
  window.addEventListener('ca-run-in-terminal', onRunInTerminal)
  window.addEventListener('ca-open-skills', openSkills)
  window.addEventListener('ca-open-git', openGit)
  window.addEventListener('ca-open-url-preview', openUrlPreviewPanel)
  window.addEventListener('ca-layout-reset', onLayoutReset)
  window.addEventListener('ca-layout-preset', onLayoutPreset as EventListener)
  window.addEventListener('ca-layout-export', onLayoutExport)
  window.addEventListener('ca-layout-import', onLayoutImport as EventListener)
  window.addEventListener('keydown', onWorkbenchKey, true)
  window.addEventListener('ca-locale', retitlePanels)
})
onUnmounted(() => {
  window.removeEventListener('click', onChatUrlClick, true)
  window.removeEventListener('auxclick', onChatUrlClick, true)
  window.removeEventListener('ca-theme', onTheme)
  window.removeEventListener('ca-menu-position', onMenuPosition as EventListener)
  window.removeEventListener('ca-focus-editor', focusEditor)
  window.removeEventListener('ca-focus-agent', focusAgent)
  window.removeEventListener('ca-open-models', openModels)
  window.removeEventListener('ca-open-search', openSearch)
  window.removeEventListener('ca-open-explorer', openExplorer)
  window.removeEventListener('ca-open-terminal', onOpenTerminal)
  window.removeEventListener('ca-run-in-terminal', onRunInTerminal)
  window.removeEventListener('ca-open-skills', openSkills)
  window.removeEventListener('ca-open-git', openGit)
  window.removeEventListener('ca-open-url-preview', openUrlPreviewPanel)
  window.removeEventListener('ca-layout-reset', onLayoutReset)
  window.removeEventListener('ca-layout-preset', onLayoutPreset as EventListener)
  window.removeEventListener('ca-layout-export', onLayoutExport)
  window.removeEventListener('ca-layout-import', onLayoutImport as EventListener)
  window.removeEventListener('keydown', onWorkbenchKey, true)
  window.removeEventListener('ca-locale', retitlePanels)
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

async function onRunInTerminal(e: Event) {
  const detail = (e as CustomEvent<TerminalRunRequest>).detail
  if (!detail?.command) return
  queueTerminalRun(detail)
  openTerminal()
  await nextTick()
  await new Promise<void>((r) => requestAnimationFrame(() => r()))
  window.dispatchEvent(new Event('ca-terminal-run'))
}

function openGit() {
  openPanel('git', 'git', panelTitle('git'))
}

function openUrlPreviewPanel() {
  openPanel('preview', 'preview', panelTitle('preview'))
}

function openSkills() {
  openPanel('skills', 'skills', panelTitle('skills'))
}

function onWorkbenchKey(e: KeyboardEvent) {
  if (e.isComposing || e.repeat) return

  // Esc → stop active run (when Agent is focused; skip modals / palette / editor / terminal)
  if (e.key === 'Escape') {
    if (paletteOpen.value || store.confirmDialog) return
    const target = e.target as HTMLElement | null
    if (target?.closest?.('.palette-root, [role="dialog"], .mention-popup, .monaco-editor, .xterm, .xterm-helper-textarea')) return
    const agentSel = '.panel-shell.agent, .agent-footer, .agent-sender-wrap, .agent-main'
    const inAgent = !!(target?.closest?.(agentSel) || (document.activeElement as HTMLElement | null)?.closest?.(agentSel))
    if (!inAgent) return
    if (!store.isRunBusy()) return
    e.preventDefault()
    void store.stop()
    return
  }

  const mod = e.metaKey || e.ctrlKey
  const key = e.key.toLowerCase()
  const target = e.target as HTMLElement | null
  const inEditable =
    target instanceof HTMLElement &&
    (!!target.closest('.monaco-editor, .xterm, .xterm-helper-textarea') ||
      target.isContentEditable ||
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA')
  const inTabStrip = !!target?.closest?.('.dv-tabs-and-actions-container, .dv-tab, .ptab')

  // Arrow keys cycle tabs within the active group when focus is on the tab strip
  if (!mod && !e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && inTabStrip) {
    e.preventDefault()
    e.stopPropagation()
    cycleActiveGroupTab(e.key === 'ArrowRight' ? 1 : -1)
    return
  }

  if (!mod || e.altKey) return

  // Ctrl/Cmd+Tab / Ctrl/Cmd+Shift+Tab → next / previous panel
  if (key === 'tab') {
    e.preventDefault()
    e.stopPropagation()
    if (e.shiftKey) dock.value?.activatePrevious({ includePanel: true })
    else dock.value?.activateNext({ includePanel: true })
    return
  }

  // Ctrl/Cmd+PageDown / PageUp → same as tab cycle (IDE habit)
  if (key === 'pagedown' || key === 'pageup') {
    e.preventDefault()
    e.stopPropagation()
    if (key === 'pageup') dock.value?.activatePrevious({ includePanel: true })
    else dock.value?.activateNext({ includePanel: true })
    return
  }

  // Ctrl/Cmd+Shift+F → search (existing)
  if (e.shiftKey && key === 'f') {
    e.preventDefault()
    store.openSearch()
    return
  }

  if (e.shiftKey && key === 'z') return

  // Ctrl/Cmd+Z → restore last explorer delete (not inside editor / terminal / inputs)
  if (key === 'z') {
    if (inEditable) return
    if (!store.canUndoFs) return
    e.preventDefault()
    e.stopPropagation()
    void store.undoFsDelete()
    return
  }

  if (e.shiftKey) return

  // Ctrl/Cmd+L → focus composer
  if (key === 'l') {
    e.preventDefault()
    focusAgent()
    window.dispatchEvent(new Event('ca-focus-composer'))
    return
  }

  // Ctrl/Cmd+N → new chat
  if (key === 'n') {
    e.preventDefault()
    void (async () => {
      await store.newChat()
      focusAgent()
      window.dispatchEvent(new Event('ca-focus-composer'))
    })()
    return
  }

  // Ctrl/Cmd+P → quick open files (not Shift+P command palette)
  if (key === 'p') {
    if (inEditable && target?.closest?.('.xterm, .xterm-helper-textarea')) return
    e.preventDefault()
    e.stopPropagation()
    paletteMode.value = 'files'
    paletteOpen.value = true
  }
}

function cycleActiveGroupTab(delta: number) {
  const api = dock.value
  const group = api?.activeGroup
  const panels = group?.panels || []
  if (panels.length < 2) return
  const activeId = group?.activePanel?.id || api?.activePanel?.id
  const index = panels.findIndex((p) => p.id === activeId)
  if (index < 0) return
  const next = panels[(index + delta + panels.length) % panels.length]
  next?.api.setActive()
  requestAnimationFrame(() => {
    const el = document.querySelector(`.dv-tab .ptab[data-panel-id="${next.id}"]`) as HTMLElement | null
    el?.focus()
  })
}

const LAYOUT_SEED = 3

function persistLayout(apiRef: DockviewApi) {
  const layout = apiRef.toJSON()
  api('/api/layout', {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: store.workspaceId, layout }),
  }).catch(() => undefined)
}

function rebuildLayout(apply: (api: DockviewApi) => void, preset?: LayoutPresetId) {
  const apiRef = dock.value
  if (!apiRef) return
  clearDock(apiRef)
  apply(apiRef)
  localStorage.setItem(layoutSeedKey(), String(LAYOUT_SEED))
  if (preset) {
    setStoredLayoutPreset(preset, store.workspaceId)
    window.dispatchEvent(new CustomEvent('ca-layout-preset-changed', { detail: { id: preset } }))
  }
  const active = apiRef.activePanel
  if (active?.id) store.activity = active.id
  persistLayout(apiRef)
}

function onLayoutReset() {
  rebuildLayout((api) => applyLayoutPreset(api, DEFAULT_LAYOUT_PRESET), DEFAULT_LAYOUT_PRESET)
}

function onLayoutPreset(e: Event) {
  const raw = (e as CustomEvent<{ id: LayoutPresetId }>).detail?.id
  const id = isLayoutPresetId(raw) ? raw : DEFAULT_LAYOUT_PRESET
  rebuildLayout((api) => applyLayoutPreset(api, id), id)
}

function onLayoutExport() {
  const apiRef = dock.value
  if (!apiRef) return
  const layout = apiRef.toJSON()
  const blob = new Blob([JSON.stringify(layout, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `code-agent-layout-${store.workspaceId || 'workspace'}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function onLayoutImport(e: Event) {
  const layout = (e as CustomEvent<{ layout: unknown }>).detail?.layout
  const apiRef = dock.value
  if (!apiRef || !layout) {
    window.dispatchEvent(new CustomEvent('ca-layout-import-result', { detail: { ok: false } }))
    return
  }
  try {
    apiRef.fromJSON(layout as never)
    localStorage.setItem(layoutSeedKey(), String(LAYOUT_SEED))
    const active = apiRef.activePanel
    if (active?.id) store.activity = active.id
    persistLayout(apiRef)
    window.dispatchEvent(new CustomEvent('ca-layout-import-result', { detail: { ok: true } }))
  } catch {
    window.dispatchEvent(new CustomEvent('ca-layout-import-result', { detail: { ok: false } }))
  }
}

function seed(apiRef: DockviewApi) {
  const preset = getStoredLayoutPreset(store.workspaceId)
  applyLayoutPreset(apiRef, preset)
  setStoredLayoutPreset(preset, store.workspaceId)
  store.activity = preset === 'code' ? 'editor' : 'agent'
}

const LEFT_PANELS = ['workspace', 'explorer', 'search'] as const
const AGENT_PANELS = ['agent', 'memory'] as const

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
  window.dispatchEvent(
    new CustomEvent('ca-layout-preset-changed', {
      detail: { id: getStoredLayoutPreset(store.workspaceId) },
    }),
  )
  await nextTick()
  requestAnimationFrame(() => {
    window.dispatchEvent(new Event('ca-layout-ready'))
  })
  event.api.onDidLayoutChange(() => {
    persistLayout(event.api)
  })
  event.api.onDidActivePanelChange((ev) => {
    if (ev?.panel?.id) store.activity = ev.panel.id
  })
}

type PanelPlace = {
  referencePanel: string
  direction: 'left' | 'right' | 'below' | 'within'
}

/** Place panels from current dock structure (works for both chat / code presets). */
function panelPosition(apiRef: DockviewApi, id: string): PanelPlace | undefined {
  if ((LEFT_PANELS as readonly string[]).includes(id)) {
    const left = findExisting(apiRef, LEFT_PANELS)
    if (left) return { referencePanel: left, direction: 'within' }
    if (apiRef.getPanel('editor')) return { referencePanel: 'editor', direction: 'left' }
    const agent = findExisting(apiRef, AGENT_PANELS)
    return agent ? { referencePanel: agent, direction: 'left' } : undefined
  }

  if (id === 'terminal') {
    if (apiRef.getPanel('editor')) return { referencePanel: 'editor', direction: 'below' }
    const agent = findExisting(apiRef, AGENT_PANELS)
    return agent ? { referencePanel: agent, direction: 'below' } : undefined
  }

  if (id === 'editor' || id === 'preview') {
    const other = id === 'preview' ? 'editor' : 'preview'
    if (apiRef.getPanel(other)) return { referencePanel: other, direction: 'within' }
    const left = findExisting(apiRef, LEFT_PANELS)
    if (left) return { referencePanel: left, direction: 'right' }
    const agent = findExisting(apiRef, AGENT_PANELS)
    return agent ? { referencePanel: agent, direction: 'left' } : undefined
  }

  if ((AGENT_PANELS as readonly string[]).includes(id)) {
    const agent = findExisting(apiRef, AGENT_PANELS)
    if (agent) return { referencePanel: agent, direction: 'within' }
    if (apiRef.getPanel('editor')) return { referencePanel: 'editor', direction: 'right' }
    return undefined
  }

  // Settings / models / git / … — keep with the agent column when present.
  const agent = findExisting(apiRef, AGENT_PANELS)
  if (agent) return { referencePanel: agent, direction: 'within' }
  if (apiRef.getPanel('editor')) return { referencePanel: 'editor', direction: 'right' }
  const left = findExisting(apiRef, LEFT_PANELS)
  return left ? { referencePanel: left, direction: 'right' } : undefined
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

function openCommandPalette() {
  paletteMode.value = 'commands'
  paletteOpen.value = true
}

function openFilePalette() {
  paletteMode.value = 'files'
  paletteOpen.value = true
}

const dockThemeClass = computed(() =>
  theme.value === 'dark' ? 'dockview-theme-dark' : 'dockview-theme-light',
)
</script>

<template>
  <div class="workbench" :class="{ 'has-desktop-titlebar': customTitleBar }">
    <DesktopTitleBar
      v-if="showDesktopStrip"
      :theme="theme"
      :show-actions="true"
      @toggle-theme="onToggleTheme"
      @open-command-palette="openCommandPalette"
    />
    <div class="workbench-shell" :class="`menu-${menuPosition}`">
      <TopMenuBar
        :theme="theme"
        :position="menuPosition"
        :as-title-bar="menuAsTitleBar"
        :hide-brand="showDesktopStrip"
        :hide-actions="showDesktopStrip"
        @open-panel="openPanel"
        @toggle-theme="onToggleTheme"
        @open-command-palette="openCommandPalette"
        @open-file-palette="openFilePalette"
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
    <AppToastHost />
    <CommandPalette
      v-model:open="paletteOpen"
      v-model:mode="paletteMode"
      @open-panel="openPanel"
      @toggle-theme="onToggleTheme"
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
.workbench-shell {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
}
.workbench-shell.menu-top {
  flex-direction: column;
}
.workbench-shell.menu-bottom {
  flex-direction: column-reverse;
}
.workbench-shell.menu-left {
  flex-direction: row;
}
.workbench-shell.menu-right {
  flex-direction: row-reverse;
}
.workbench-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
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
</style>
