import type { DockviewApi } from 'dockview-vue'
import { panelTitle } from '@/i18n'

export type LayoutPresetId = 'chat' | 'code'

export const LAYOUT_PRESET_IDS: LayoutPresetId[] = ['chat', 'code']

export const DEFAULT_LAYOUT_PRESET: LayoutPresetId = 'chat'

export function isLayoutPresetId(value: unknown): value is LayoutPresetId {
  return value === 'chat' || value === 'code'
}

export function layoutPresetStorageKey(workspaceId?: string | null) {
  return `ca.layout.preset.${workspaceId || 'default'}`
}

export function getStoredLayoutSelection(workspaceId?: string | null): string {
  try {
    const raw = localStorage.getItem(layoutPresetStorageKey(workspaceId))
    if (isLayoutPresetId(raw)) return raw
    if (typeof raw === 'string' && raw && getSavedLayout(raw, workspaceId)) return raw
    return DEFAULT_LAYOUT_PRESET
  } catch {
    return DEFAULT_LAYOUT_PRESET
  }
}

export function setStoredLayoutSelection(id: string, workspaceId?: string | null) {
  try {
    localStorage.setItem(layoutPresetStorageKey(workspaceId), id)
  } catch {
    /* ignore quota */
  }
}

export function getStoredLayoutPreset(workspaceId?: string | null): LayoutPresetId {
  const raw = getStoredLayoutSelection(workspaceId)
  return isLayoutPresetId(raw) ? raw : DEFAULT_LAYOUT_PRESET
}

export function setStoredLayoutPreset(id: LayoutPresetId, workspaceId?: string | null) {
  setStoredLayoutSelection(id, workspaceId)
}

export type SavedLayout = {
  id: string
  name: string
  layout: unknown
  panelIds: string[]
  updatedAt: number
}

export const SAVED_LAYOUT_NAME_MAX = 40

function savedLayoutsKey(workspaceId?: string | null) {
  return `ca.layout.named.${workspaceId || 'default'}`
}

function isSavedLayout(value: unknown): value is SavedLayout {
  if (!value || typeof value !== 'object') return false
  const item = value as SavedLayout
  return (
    typeof item.id === 'string' &&
    Boolean(item.id) &&
    typeof item.name === 'string' &&
    Array.isArray(item.panelIds) &&
    item.layout != null
  )
}

export function listSavedLayouts(workspaceId?: string | null): SavedLayout[] {
  try {
    const raw = localStorage.getItem(savedLayoutsKey(workspaceId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(isSavedLayout)
      .map((item) => ({
        id: item.id,
        name: item.name,
        layout: item.layout,
        panelIds: item.panelIds.map(String),
        updatedAt: typeof item.updatedAt === 'number' ? item.updatedAt : 0,
      }))
      .sort((a, b) => b.updatedAt - a.updatedAt)
  } catch {
    return []
  }
}

function writeSavedLayouts(items: SavedLayout[], workspaceId?: string | null) {
  try {
    localStorage.setItem(savedLayoutsKey(workspaceId), JSON.stringify(items))
  } catch {
    /* ignore quota */
  }
}

export function getSavedLayout(id: string, workspaceId?: string | null): SavedLayout | null {
  return listSavedLayouts(workspaceId).find((item) => item.id === id) || null
}

export function findSavedLayoutByName(name: string, workspaceId?: string | null): SavedLayout | null {
  const trimmed = name.trim()
  if (!trimmed) return null
  return listSavedLayouts(workspaceId).find((item) => item.name === trimmed) || null
}

export function createSavedLayoutId() {
  return `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

export function upsertSavedLayout(entry: SavedLayout, workspaceId?: string | null): SavedLayout[] {
  const items = listSavedLayouts(workspaceId).filter((item) => item.id !== entry.id)
  items.unshift(entry)
  writeSavedLayouts(items, workspaceId)
  return listSavedLayouts(workspaceId)
}

export function deleteSavedLayout(id: string, workspaceId?: string | null): SavedLayout[] {
  const items = listSavedLayouts(workspaceId).filter((item) => item.id !== id)
  writeSavedLayouts(items, workspaceId)
  return items
}

export function samePanelSet(a: readonly string[], b: readonly string[]) {
  if (a.length !== b.length) return false
  const have = new Set(a)
  return b.every((id) => have.has(id))
}

export function matchSavedLayout(
  panelIds: string[],
  workspaceId?: string | null,
  preferredId?: string | null,
): SavedLayout | null {
  const saved = listSavedLayouts(workspaceId)
  if (preferredId) {
    const preferred = saved.find((item) => item.id === preferredId)
    if (preferred && samePanelSet(preferred.panelIds, panelIds)) return preferred
  }
  return saved.find((item) => samePanelSet(item.panelIds, panelIds)) || null
}

export function emitNamedLayoutsChanged(workspaceId?: string | null) {
  window.dispatchEvent(
    new CustomEvent('ca-layout-named-changed', {
      detail: { saved: listSavedLayouts(workspaceId) },
    }),
  )
}

export const PRESET_PANEL_IDS: Record<LayoutPresetId, readonly string[]> = {
  chat: ['workspace', 'agent'],
  code: ['workspace', 'explorer', 'search', 'git', 'editor', 'terminal', 'debug', 'agent', 'memory'],
}

export function layoutSnapshotKey(id: LayoutPresetId, workspaceId?: string | null) {
  return `ca.layout.snap.${workspaceId || 'default'}.${id}`
}

export function getStoredLayoutSnapshot(id: LayoutPresetId, workspaceId?: string | null): unknown | null {
  try {
    const raw = localStorage.getItem(layoutSnapshotKey(id, workspaceId))
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function setStoredLayoutSnapshot(
  id: LayoutPresetId,
  layout: unknown,
  workspaceId?: string | null,
) {
  try {
    localStorage.setItem(layoutSnapshotKey(id, workspaceId), JSON.stringify(layout))
  } catch {
    /* ignore quota */
  }
}

export function clearStoredLayoutSnapshots(workspaceId?: string | null) {
  for (const id of LAYOUT_PRESET_IDS) {
    try {
      localStorage.removeItem(layoutSnapshotKey(id, workspaceId))
    } catch {
      /* ignore */
    }
  }
}

export function isLayoutDirty(panelIds: string[], preset: LayoutPresetId) {
  const expected = PRESET_PANEL_IDS[preset]
  if (panelIds.length !== expected.length) return true
  const have = new Set(panelIds)
  return expected.some((id) => !have.has(id))
}

export function matchLayoutPreset(panelIds: string[]): LayoutPresetId | null {
  for (const id of LAYOUT_PRESET_IDS) {
    if (!isLayoutDirty(panelIds, id)) return id
  }
  return null
}

export type LayoutViewState = {
  id: string
  dirty: boolean
  saved: SavedLayout[]
}

export function emitLayoutState(state: LayoutViewState) {
  window.dispatchEvent(new CustomEvent('ca-layout-state', { detail: state }))
}

/** Remove all dock panels so a preset can rebuild from scratch. */
export function clearDock(api: DockviewApi) {
  for (const panel of [...api.panels]) {
    try {
      panel.api.close()
    } catch {
      /* ignore */
    }
  }
}

/** 对话优先：左工作空间 | 右 Agent。 */
export function applyChatPreset(api: DockviewApi) {
  api.addPanel({ id: 'agent', component: 'agent', title: panelTitle('agent') })
  api.addPanel({
    id: 'workspace',
    component: 'workspace',
    title: panelTitle('workspace'),
    position: { referencePanel: 'agent', direction: 'left' },
    initialWidth: 280,
  })
  api.getPanel('agent')?.api.setActive()
}

/** 编码优先：左 工作空间/文件/搜索/Git | 中 上编辑器 / 下终端+调试 | 右 Agent+记忆。 */
export function applyCodePreset(api: DockviewApi) {
  api.addPanel({ id: 'editor', component: 'editor', title: panelTitle('editor') })
  api.addPanel({
    id: 'workspace',
    component: 'workspace',
    title: panelTitle('workspace'),
    position: { referencePanel: 'editor', direction: 'left' },
    initialWidth: 260,
  })
  api.addPanel({
    id: 'explorer',
    component: 'explorer',
    title: panelTitle('explorer'),
    position: { referencePanel: 'workspace', direction: 'within' },
    inactive: true,
  })
  api.addPanel({
    id: 'search',
    component: 'search',
    title: panelTitle('search'),
    position: { referencePanel: 'workspace', direction: 'within' },
    inactive: true,
  })
  api.addPanel({
    id: 'git',
    component: 'git',
    title: panelTitle('git'),
    position: { referencePanel: 'workspace', direction: 'within' },
    inactive: true,
  })
  api.addPanel({
    id: 'agent',
    component: 'agent',
    title: panelTitle('agent'),
    position: { referencePanel: 'editor', direction: 'right' },
    initialWidth: 380,
  })
  api.addPanel({
    id: 'memory',
    component: 'memory',
    title: panelTitle('memory'),
    position: { referencePanel: 'agent', direction: 'within' },
    inactive: true,
  })
  api.addPanel({
    id: 'terminal',
    component: 'terminal',
    title: panelTitle('terminal'),
    position: { referencePanel: 'editor', direction: 'below' },
    initialHeight: 200,
  })
  api.addPanel({
    id: 'debug',
    component: 'debug',
    title: panelTitle('debug'),
    position: { referencePanel: 'terminal', direction: 'within' },
    inactive: true,
  })
  api.getPanel('editor')?.api.setActive()
}

export function applyLayoutPreset(api: DockviewApi, id: LayoutPresetId) {
  if (id === 'code') applyCodePreset(api)
  else applyChatPreset(api)
}
