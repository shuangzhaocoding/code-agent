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

export function getStoredLayoutPreset(workspaceId?: string | null): LayoutPresetId {
  try {
    const raw = localStorage.getItem(layoutPresetStorageKey(workspaceId))
    return isLayoutPresetId(raw) ? raw : DEFAULT_LAYOUT_PRESET
  } catch {
    return DEFAULT_LAYOUT_PRESET
  }
}

export function setStoredLayoutPreset(id: LayoutPresetId, workspaceId?: string | null) {
  try {
    localStorage.setItem(layoutPresetStorageKey(workspaceId), id)
  } catch {
    /* ignore quota */
  }
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

/** 对话优先：宽对话区居中，文件侧栏在左。 */
export function applyChatPreset(api: DockviewApi) {
  api.addPanel({ id: 'agent', component: 'agent', title: panelTitle('agent') })
  api.addPanel({
    id: 'memory',
    component: 'memory',
    title: panelTitle('memory'),
    position: { referencePanel: 'agent', direction: 'within' },
  })
  api.addPanel({
    id: 'workspace',
    component: 'workspace',
    title: panelTitle('workspace'),
    position: { referencePanel: 'agent', direction: 'left' },
  })
  api.addPanel({
    id: 'explorer',
    component: 'explorer',
    title: panelTitle('explorer'),
    position: { referencePanel: 'workspace', direction: 'within' },
  })
  api.addPanel({
    id: 'search',
    component: 'search',
    title: panelTitle('search'),
    position: { referencePanel: 'workspace', direction: 'within' },
  })
  api.getPanel('agent')?.api.setActive()
}

/** 编码优先：资源管理器 | 编辑器（下挂终端）| 对话。 */
export function applyCodePreset(api: DockviewApi) {
  api.addPanel({ id: 'editor', component: 'editor', title: panelTitle('editor') })
  api.addPanel({
    id: 'workspace',
    component: 'workspace',
    title: panelTitle('workspace'),
    position: { referencePanel: 'editor', direction: 'left' },
  })
  api.addPanel({
    id: 'explorer',
    component: 'explorer',
    title: panelTitle('explorer'),
    position: { referencePanel: 'workspace', direction: 'within' },
  })
  api.addPanel({
    id: 'search',
    component: 'search',
    title: panelTitle('search'),
    position: { referencePanel: 'workspace', direction: 'within' },
  })
  api.addPanel({
    id: 'terminal',
    component: 'terminal',
    title: panelTitle('terminal'),
    position: { referencePanel: 'editor', direction: 'below' },
  })
  api.addPanel({
    id: 'agent',
    component: 'agent',
    title: panelTitle('agent'),
    position: { referencePanel: 'editor', direction: 'right' },
  })
  api.addPanel({
    id: 'memory',
    component: 'memory',
    title: panelTitle('memory'),
    position: { referencePanel: 'agent', direction: 'within' },
  })
  api.getPanel('editor')?.api.setActive()
}

export function applyLayoutPreset(api: DockviewApi, id: LayoutPresetId) {
  if (id === 'code') applyCodePreset(api)
  else applyChatPreset(api)
}
