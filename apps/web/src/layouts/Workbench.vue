<script setup lang="ts">
import { DockviewVue, type VueComponent } from 'dockview-vue'
import type { DockviewApi, DockviewReadyEvent } from 'dockview-vue'
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, shallowRef, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { panelTitle } from '@/i18n'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import { currentTheme, toggleTheme, type Theme } from '@/theme'
import AgentPanel from '@/panels/AgentPanel.vue'
import TopMenuBar from '@/components/TopMenuBar.vue'
import DesktopTitleBar from '@/components/DesktopTitleBar.vue'
import PanelTab from '@/components/PanelTab.vue'
import ConfirmCard from '@/components/ConfirmCard.vue'
import PromptCard from '@/components/PromptCard.vue'
import PortNotifyToast from '@/components/PortNotifyToast.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import AppToastHost from '@/components/AppToastHost.vue'
import { useToast } from '@/composables/useToast'
import {
  applyLayoutPreset,
  clearDock,
  clearStoredLayoutSnapshots,
  createSavedLayoutId,
  DEFAULT_LAYOUT_PRESET,
  deleteSavedLayout,
  emitLayoutState,
  emitNamedLayoutsChanged,
  findSavedLayoutByName,
  getSavedLayout,
  getStoredLayoutPreset,
  getStoredLayoutSelection,
  getStoredLayoutSnapshot,
  isLayoutPresetId,
  listSavedLayouts,
  matchLayoutPreset,
  matchSavedLayout,
  samePanelSet,
  SAVED_LAYOUT_NAME_MAX,
  setStoredLayoutPreset,
  setStoredLayoutSelection,
  setStoredLayoutSnapshot,
  upsertSavedLayout,
  type LayoutPresetId,
  type SavedLayout,
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
const DebugPanel = defineAsyncComponent(() => import('@/panels/DebugPanel.vue'))
const UrlPreviewPanel = defineAsyncComponent(() => import('@/panels/UrlPreviewPanel.vue'))
const MemoryPanel = defineAsyncComponent(() => import('@/panels/MemoryPanel.vue'))
const ContextDebugPanel = defineAsyncComponent(() => import('@/panels/ContextDebugPanel.vue'))
const CheckpointsPanel = defineAsyncComponent(() => import('@/panels/CheckpointsPanel.vue'))

const { t } = useI18n()
const toast = useToast()
const store = useAppStore()
const theme = ref<Theme>(currentTheme())
const menuPosition = ref<MenuBarPosition>(getMenuBarPosition())
const paletteOpen = ref(false)
const paletteMode = ref<'commands' | 'files'>('commands')
const paletteSeedQuery = ref('')
const customTitleBar = computed(() => hasCustomTitleBar())
const menuAsTitleBar = computed(() => customTitleBar.value && menuPosition.value === 'top')
const showDesktopStrip = computed(() => customTitleBar.value && menuPosition.value !== 'top')

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
  debug: DebugPanel,
  preview: UrlPreviewPanel,
  memory: MemoryPanel,
  contextDebug: ContextDebugPanel,
  checkpoints: CheckpointsPanel,
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
  window.addEventListener('ca-follow-editor', onFollowEditor as EventListener)
  window.addEventListener('ca-open-review', onOpenReview as EventListener)
  window.addEventListener('ca-focus-agent', focusAgent)
  window.addEventListener('ca-open-models', openModels)
  window.addEventListener('ca-open-search', openSearch)
  window.addEventListener('ca-open-explorer', openExplorer)
  window.addEventListener('ca-open-terminal', onOpenTerminal)
  window.addEventListener('ca-close-terminal', closeTerminalPanel)
  window.addEventListener('ca-terminal-shortcut-new', onTerminalShortcutNew)
  window.addEventListener('ca-run-in-terminal', onRunInTerminal)
  window.addEventListener('ca-open-panel', onOpenPanelEvent as EventListener)
  window.addEventListener('ca-open-skills', openSkills)
  window.addEventListener('ca-open-git', openGit)
  window.addEventListener('ca-open-url-preview', openUrlPreviewPanel)
  window.addEventListener('ca-layout-reset', onLayoutReset)
  window.addEventListener('ca-layout-preset', onLayoutPreset as EventListener)
  window.addEventListener('ca-layout-save', onLayoutSave)
  window.addEventListener('ca-layout-named-delete', onLayoutNamedDelete as EventListener)
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
  window.removeEventListener('ca-follow-editor', onFollowEditor as EventListener)
  window.removeEventListener('ca-open-review', onOpenReview as EventListener)
  window.removeEventListener('ca-focus-agent', focusAgent)
  window.removeEventListener('ca-open-models', openModels)
  window.removeEventListener('ca-open-search', openSearch)
  window.removeEventListener('ca-open-explorer', openExplorer)
  window.removeEventListener('ca-open-terminal', onOpenTerminal)
  window.removeEventListener('ca-close-terminal', closeTerminalPanel)
  window.removeEventListener('ca-terminal-shortcut-new', onTerminalShortcutNew)
  window.removeEventListener('ca-run-in-terminal', onRunInTerminal)
  window.removeEventListener('ca-open-panel', onOpenPanelEvent as EventListener)
  window.removeEventListener('ca-open-skills', openSkills)
  window.removeEventListener('ca-open-git', openGit)
  window.removeEventListener('ca-open-url-preview', openUrlPreviewPanel)
  window.removeEventListener('ca-layout-reset', onLayoutReset)
  window.removeEventListener('ca-layout-preset', onLayoutPreset as EventListener)
  window.removeEventListener('ca-layout-save', onLayoutSave)
  window.removeEventListener('ca-layout-named-delete', onLayoutNamedDelete as EventListener)
  window.removeEventListener('ca-layout-export', onLayoutExport)
  window.removeEventListener('ca-layout-import', onLayoutImport as EventListener)
  window.removeEventListener('keydown', onWorkbenchKey, true)
  window.removeEventListener('ca-locale', retitlePanels)
})

let applyingLayout = false
let quietEditorFocus = false
let followTimer: ReturnType<typeof setTimeout> | null = null
let followPath = ''

function focusEditor() {
  if (quietEditorFocus) {
    ensurePanel('editor', 'editor', panelTitle('editor'), false)
    return
  }
  openPanel('editor', 'editor', panelTitle('editor'))
}

function focusAgent() {
  openPanel('agent', 'agent', panelTitle('agent'))
}

async function openFollowedFile(path: string) {
  const apiRef = dock.value
  const prev = apiRef?.activePanel?.id
  quietEditorFocus = true
  try {
    ensurePanel('editor', 'editor', panelTitle('editor'), false)
    await store.openChatFilePath(path)
  } finally {
    quietEditorFocus = false
    if (prev && prev !== 'editor') apiRef?.getPanel(prev)?.api.setActive()
  }
}

function onFollowEditor(e: Event) {
  const path = String((e as CustomEvent<{ path?: string }>).detail?.path || '')
  if (!path) return
  followPath = path
  if (followTimer) clearTimeout(followTimer)
  followTimer = setTimeout(() => {
    followTimer = null
    const next = followPath
    followPath = ''
    if (next) void openFollowedFile(next)
  }, 80)
}

async function onOpenReview(e: Event) {
  const path = String((e as CustomEvent<{ path?: string }>).detail?.path || '')
  openPanel('editor', 'editor', panelTitle('editor'))
  if (path) await store.openChatFilePath(path)
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

function closeTerminalPanel() {
  dock.value?.getPanel('terminal')?.api.close()
}

async function newTerminalTab() {
  const existed = Boolean(dock.value?.getPanel('terminal'))
  openTerminal()
  await nextTick()
  await new Promise<void>((r) => requestAnimationFrame(() => r()))
  // Fresh mount already creates/restores tabs in TerminalPanel.loadExisting().
  if (existed) window.dispatchEvent(new Event('ca-terminal-new'))
}

function onTerminalShortcutNew() {
  void newTerminalTab()
}

function closeActiveTerminalTab() {
  window.dispatchEvent(new Event('ca-terminal-close-tab'))
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

function onOpenPanelEvent(e: Event) {
  const id = (e as CustomEvent<{ id?: string }>).detail?.id
  if (!id) return
  openPanel(id, id, panelTitle(id))
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

  // Ctrl/Cmd+` → open/focus terminal; Ctrl/Cmd+Shift+` → new terminal tab
  if (e.code === 'Backquote' || key === '`' || key === '~') {
    e.preventDefault()
    e.stopPropagation()
    if (e.shiftKey) void newTerminalTab()
    else openTerminal()
    return
  }

  // Ctrl/Cmd+W → close active terminal tab when focus is in the terminal panel
  if (key === 'w' && !e.shiftKey) {
    const inTerminal = !!target?.closest?.('.term-panel, .xterm, .xterm-helper-textarea')
    if (inTerminal) {
      e.preventDefault()
      e.stopPropagation()
      closeActiveTerminalTab()
      return
    }
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
    paletteSeedQuery.value = ''
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

const LAYOUT_SEED = 6

function persistLayout(apiRef: DockviewApi) {
  const layout = apiRef.toJSON()
  api('/api/layout', {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: store.workspaceId, layout }),
  }).catch(() => undefined)
}

function panelIdsOf(apiRef: DockviewApi) {
  return apiRef.panels.map((panel) => panel.id)
}

function currentSelectionId() {
  return getStoredLayoutSelection(store.workspaceId)
}

function refreshLayoutState(apiRef?: DockviewApi | null) {
  const api = apiRef || dock.value
  if (!api) return
  const ws = store.workspaceId
  const ids = panelIdsOf(api)
  const stored = currentSelectionId()
  const saved = listSavedLayouts(ws)
  const named = matchSavedLayout(ids, ws, stored)
  if (!isLayoutPresetId(stored) && named && named.id === stored) {
    setStoredLayoutSelection(named.id, ws)
    emitLayoutState({ id: named.id, dirty: false, saved })
    return
  }
  const builtin = matchLayoutPreset(ids)
  if (builtin) {
    setStoredLayoutSelection(builtin, ws)
    emitLayoutState({ id: builtin, dirty: false, saved })
    return
  }
  if (named) {
    setStoredLayoutSelection(named.id, ws)
    emitLayoutState({ id: named.id, dirty: false, saved })
    return
  }
  emitLayoutState({ id: stored, dirty: true, saved })
}

function notifyLayoutApplied(id: LayoutPresetId) {
  window.dispatchEvent(new CustomEvent('ca-layout-preset-applied', { detail: { id, reset: true } }))
  toast.success(t('layout.presetApplied', { name: t(`layout.presets.${id}`) }))
}

function saveViewSnapshot(apiRef: DockviewApi, id: LayoutPresetId) {
  try {
    setStoredLayoutSnapshot(id, apiRef.toJSON(), store.workspaceId)
  } catch {
    /* ignore */
  }
}

function rebuildLayout(apply: (api: DockviewApi) => void, selection?: string) {
  const apiRef = dock.value
  if (!apiRef) return
  applyingLayout = true
  clearDock(apiRef)
  apply(apiRef)
  localStorage.setItem(layoutSeedKey(), String(LAYOUT_SEED))
  if (selection) {
    setStoredLayoutSelection(selection, store.workspaceId)
    window.dispatchEvent(new CustomEvent('ca-layout-preset-changed', { detail: { id: selection } }))
    if (isLayoutPresetId(selection)) saveViewSnapshot(apiRef, selection)
  }
  const active = apiRef.activePanel
  if (active?.id) store.activity = active.id
  persistLayout(apiRef)
  applyingLayout = false
  refreshLayoutState(apiRef)
}

function switchLayoutView(id: LayoutPresetId, opts?: { force?: boolean }) {
  const apiRef = dock.value
  if (!apiRef) return
  const matched = matchLayoutPreset(panelIdsOf(apiRef))
  if (!opts?.force && matched === id) return
  rebuildLayout((api) => applyLayoutPreset(api, id), id)
  notifyLayoutApplied(id)
}

function switchNamedLayout(id: string, opts?: { force?: boolean }) {
  const apiRef = dock.value
  const saved = getSavedLayout(id, store.workspaceId)
  if (!apiRef || !saved) return
  if (!opts?.force && currentSelectionId() === id && samePanelSet(saved.panelIds, panelIdsOf(apiRef))) return
  applyingLayout = true
  try {
    apiRef.fromJSON(saved.layout as never)
  } catch {
    applyingLayout = false
    toast.error(t('layout.importInvalid'))
    return
  }
  localStorage.setItem(layoutSeedKey(), String(LAYOUT_SEED))
  setStoredLayoutSelection(id, store.workspaceId)
  window.dispatchEvent(new CustomEvent('ca-layout-preset-changed', { detail: { id } }))
  const active = apiRef.activePanel
  if (active?.id) store.activity = active.id
  persistLayout(apiRef)
  applyingLayout = false
  refreshLayoutState(apiRef)
  toast.success(t('layout.presetApplied', { name: saved.name }))
}

function onLayoutReset() {
  const id = currentSelectionId()
  if (isLayoutPresetId(id)) switchLayoutView(id, { force: true })
  else switchNamedLayout(id, { force: true })
}

function onLayoutPreset(e: Event) {
  const id = (e as CustomEvent<{ id?: string }>).detail?.id
  if (isLayoutPresetId(id)) {
    switchLayoutView(id)
    return
  }
  if (id && getSavedLayout(id, store.workspaceId)) {
    switchNamedLayout(id)
    return
  }
  switchLayoutView(DEFAULT_LAYOUT_PRESET)
}

async function onLayoutSave() {
  const apiRef = dock.value
  if (!apiRef) return
  const ws = store.workspaceId
  const stored = currentSelectionId()
  const currentSaved = isLayoutPresetId(stored) ? null : getSavedLayout(stored, ws)
  const raw = await store.askPrompt({
    title: t('layout.saveTitle'),
    summary: t('layout.saveSummary'),
    label: t('layout.saveLabel'),
    placeholder: t('layout.savePlaceholder'),
    defaultValue: currentSaved?.name || '',
    confirmLabel: t('common.save'),
  })
  if (raw == null) return
  const name = raw.trim().slice(0, SAVED_LAYOUT_NAME_MAX)
  if (!name) {
    toast.error(t('layout.nameRequired'))
    return
  }
  const byName = findSavedLayoutByName(name, ws)
  let id = currentSaved && currentSaved.name === name ? currentSaved.id : byName?.id
  if (byName && byName.id !== currentSaved?.id) {
    const ok = await store.askConfirm({
      title: t('layout.saveOverwriteTitle'),
      summary: t('layout.saveOverwrite', { name }),
    })
    if (!ok) return
    id = byName.id
  }
  const entry: SavedLayout = {
    id: id || createSavedLayoutId(),
    name,
    layout: apiRef.toJSON(),
    panelIds: panelIdsOf(apiRef),
    updatedAt: Date.now(),
  }
  upsertSavedLayout(entry, ws)
  setStoredLayoutSelection(entry.id, ws)
  emitNamedLayoutsChanged(ws)
  persistLayout(apiRef)
  refreshLayoutState(apiRef)
  toast.success(t('layout.saveDone', { name }))
}

async function onLayoutNamedDelete(e: Event) {
  const id = (e as CustomEvent<{ id?: string }>).detail?.id
  const ws = store.workspaceId
  const saved = id ? getSavedLayout(id, ws) : null
  if (!saved || !id) return
  const ok = await store.askConfirm({
    title: t('layout.deleteTitle'),
    summary: t('layout.deleteSummary', { name: saved.name }),
    danger: true,
    confirmLabel: t('common.delete'),
  })
  if (!ok) return
  deleteSavedLayout(id, ws)
  if (currentSelectionId() === id) {
    const builtin = dock.value ? matchLayoutPreset(panelIdsOf(dock.value)) : null
    setStoredLayoutSelection(builtin || DEFAULT_LAYOUT_PRESET, ws)
  }
  emitNamedLayoutsChanged(ws)
  refreshLayoutState(dock.value)
  toast.success(t('layout.deleteDone', { name: saved.name }))
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
    const view = currentSelectionId()
    if (isLayoutPresetId(view)) saveViewSnapshot(apiRef, view)
    refreshLayoutState(apiRef)
    window.dispatchEvent(new CustomEvent('ca-layout-import-result', { detail: { ok: true } }))
  } catch {
    window.dispatchEvent(new CustomEvent('ca-layout-import-result', { detail: { ok: false } }))
  }
}

function seed(apiRef: DockviewApi) {
  clearStoredLayoutSnapshots(store.workspaceId)
  const preset = getStoredLayoutPreset(store.workspaceId)
  applyLayoutPreset(apiRef, preset)
  setStoredLayoutPreset(preset, store.workspaceId)
  saveViewSnapshot(apiRef, preset)
  store.activity = preset === 'code' ? 'editor' : 'agent'
}

const LEFT_PANELS = ['workspace', 'explorer', 'search', 'git'] as const
const BOTTOM_PANELS = ['terminal', 'debug'] as const
const AGENT_PANELS = ['agent', 'memory', 'contextDebug', 'checkpoints'] as const

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
    const view = currentSelectionId()
    if (isLayoutPresetId(view) && !getStoredLayoutSnapshot(view, store.workspaceId)) {
      saveViewSnapshot(event.api, view)
    }
  }
  window.dispatchEvent(
    new CustomEvent('ca-layout-preset-changed', {
      detail: { id: currentSelectionId() },
    }),
  )
  refreshLayoutState(event.api)
  await nextTick()
  requestAnimationFrame(() => {
    window.dispatchEvent(new Event('ca-layout-ready'))
  })
  event.api.onDidLayoutChange(() => {
    if (applyingLayout) return
    persistLayout(event.api)
    const view = currentSelectionId()
    if (isLayoutPresetId(view)) saveViewSnapshot(event.api, view)
    refreshLayoutState(event.api)
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

  if ((BOTTOM_PANELS as readonly string[]).includes(id)) {
    const bottom = findExisting(apiRef, BOTTOM_PANELS)
    if (bottom) return { referencePanel: bottom, direction: 'within' }
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

  // Settings / models / plugins — keep with the agent column when present.
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

function ensurePanel(id: string, component: string, title: string, activate = true) {
  const apiRef = dock.value
  if (!apiRef) return
  const existing = apiRef.getPanel(id)
  if (existing) {
    if (!existing.api.group.api.isVisible) existing.api.group.api.setVisible(true)
    if (activate) {
      existing.api.setActive()
      store.activity = id
    }
    return
  }
  const place = panelPosition(apiRef, id)
  apiRef.addPanel({
    id,
    component,
    title,
    ...(place ? { position: place } : {}),
  })
  if (activate) store.activity = id
}

function openPanel(id: string, component: string, title: string) {
  ensurePanel(id, component, title, true)
}

function onToggleTheme() {
  theme.value = toggleTheme()
}

function openCommandPalette(seedQuery = '') {
  paletteMode.value = 'commands'
  paletteSeedQuery.value = seedQuery
  paletteOpen.value = true
}

function openFilePalette() {
  paletteMode.value = 'files'
  paletteSeedQuery.value = ''
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
    <PromptCard
      v-if="store.promptDialog"
      :title="store.promptDialog.title"
      :summary="store.promptDialog.summary"
      :label="store.promptDialog.label"
      :default-value="store.promptDialog.defaultValue"
      :placeholder="store.promptDialog.placeholder"
      :confirm-label="store.promptDialog.confirmLabel"
      :cancel-label="store.promptDialog.cancelLabel"
      :danger="store.promptDialog.danger === true"
      @confirm="store.closePrompt($event)"
      @cancel="store.closePrompt(null)"
    />
    <PortNotifyToast />
    <AppToastHost />
    <CommandPalette
      v-model:open="paletteOpen"
      v-model:mode="paletteMode"
      :seed-query="paletteSeedQuery"
      @open-panel="openPanel"
      @toggle-theme="onToggleTheme"
    />
  </div>
</template>

<style scoped>
.workbench {
  position: relative;
  z-index: 1;
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
.dock :deep(.dv-right-actions-container) {
  display: flex;
  align-items: center;
}
</style>
