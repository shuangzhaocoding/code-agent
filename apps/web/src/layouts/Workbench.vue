<script setup lang="ts">
import { DockviewVue } from 'dockview-vue'
import type { DockviewApi, DockviewReadyEvent } from 'dockview-vue'
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import { currentTheme, toggleTheme, type Theme } from '@/theme'
import AppIcon from '@/components/AppIcon.vue'
import PanelTab from '@/components/PanelTab.vue'
import WorkspaceSwitch from '@/components/WorkspaceSwitch.vue'
import ExplorerPanel from '@/panels/ExplorerPanel.vue'
import EditorPanel from '@/panels/EditorPanel.vue'
import AgentPanel from '@/panels/AgentPanel.vue'
import TerminalPanel from '@/panels/TerminalPanel.vue'
import ChatListPanel from '@/panels/ChatListPanel.vue'
import SkillsPanel from '@/panels/SkillsPanel.vue'
import ModelsPanel from '@/panels/ModelsPanel.vue'
import SettingsPanel from '@/panels/SettingsPanel.vue'
import ConfirmCard from '@/components/ConfirmCard.vue'
import GitPanel from '@/panels/GitPanel.vue'

const store = useAppStore()
const theme = ref<Theme>(currentTheme())
const components = {
  explorer: ExplorerPanel,
  editor: EditorPanel,
  agent: AgentPanel,
  terminal: TerminalPanel,
  chats: ChatListPanel,
  skills: SkillsPanel,
  models: ModelsPanel,
  settings: SettingsPanel,
  git: GitPanel,
}

const dock = ref<DockviewApi | null>(null)
const regions = ref({ explorer: true, terminal: true, agent: true })
const workspaceOpen = ref(false)

function onTheme(e: Event) {
  theme.value = (e as CustomEvent<Theme>).detail
}

onMounted(() => {
  window.addEventListener('ca-theme', onTheme)
  window.addEventListener('ca-focus-editor', focusEditor)
})
onUnmounted(() => {
  window.removeEventListener('ca-theme', onTheme)
  window.removeEventListener('ca-focus-editor', focusEditor)
})

function showHeaders(apiRef: DockviewApi) {
  for (const group of apiRef.groups) {
    group.model.header.hidden = false
  }
}

function focusEditor() {
  openPanel('editor', 'editor', '编辑器')
}

function seed(apiRef: DockviewApi) {
  apiRef.addPanel({ id: 'explorer', component: 'explorer', title: '文件' })
  apiRef.addPanel({
    id: 'editor',
    component: 'editor',
    title: '编辑器',
    position: { referencePanel: 'explorer', direction: 'right' },
  })
  apiRef.addPanel({
    id: 'agent',
    component: 'agent',
    title: 'Agent',
    position: { referencePanel: 'editor', direction: 'right' },
  })
  apiRef.addPanel({
    id: 'terminal',
    component: 'terminal',
    title: '终端',
    position: { referencePanel: 'editor', direction: 'below' },
  })
}

function syncRegions() {
  const apiRef = dock.value
  if (!apiRef) return
  regions.value = {
    explorer: isRegionVisible(apiRef, 'explorer'),
    terminal: isRegionVisible(apiRef, 'terminal'),
    agent: isRegionVisible(apiRef, 'agent'),
  }
}

function isRegionVisible(apiRef: DockviewApi, id: string) {
  const panel = apiRef.getPanel(id)
  if (!panel) return false
  return panel.api.group.api.isVisible
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
  showHeaders(event.api)
  syncRegions()
  event.api.onDidLayoutChange(() => {
    syncRegions()
    const layout = event.api.toJSON()
    api('/api/layout', {
      method: 'PUT',
      body: JSON.stringify({ workspace_id: store.workspaceId, layout }),
    }).catch(() => undefined)
  })
}

const placements: Record<string, { referencePanel: string; direction: 'left' | 'right' | 'below' }> = {
  explorer: { referencePanel: 'editor', direction: 'left' },
  terminal: { referencePanel: 'editor', direction: 'below' },
  agent: { referencePanel: 'editor', direction: 'right' },
  chats: { referencePanel: 'explorer', direction: 'below' },
  git: { referencePanel: 'explorer', direction: 'below' },
}

function openPanel(id: string, component: string, title: string) {
  const apiRef = dock.value
  if (!apiRef) return
  const existing = apiRef.getPanel(id)
  if (existing) {
    if (!existing.api.group.api.isVisible) existing.api.group.api.setVisible(true)
    existing.api.setActive()
    store.activity = id
    syncRegions()
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
  syncRegions()
}

function toggleRegion(id: 'explorer' | 'terminal' | 'agent') {
  const apiRef = dock.value
  if (!apiRef) return
  const panel = apiRef.getPanel(id)
  if (panel) {
    const group = panel.api.group
    if (group.panels.length <= 1) {
      group.api.setVisible(!group.api.isVisible)
      if (group.api.isVisible) panel.api.setActive()
    } else if (group.api.isVisible) {
      panel.api.close()
    }
  } else {
    const meta = items.find((item) => item.id === id)
    if (meta) openPanel(meta.id, meta.component, meta.title)
  }
  syncRegions()
}

const items = [
  { id: 'explorer', component: 'explorer', title: '文件', label: '文件', icon: 'folder' },
  { id: 'git', component: 'git', title: 'Git', label: 'Git', icon: 'git' },
  { id: 'chats', component: 'chats', title: '会话', label: '会话', icon: 'chat' },
  { id: 'agent', component: 'agent', title: 'Agent', label: 'Agent', icon: 'spark' },
  { id: 'terminal', component: 'terminal', title: '终端', label: '终端', icon: 'terminal' },
  { id: 'skills', component: 'skills', title: 'Skill', label: 'Skill', icon: 'book' },
  { id: 'models', component: 'models', title: '模型', label: '模型', icon: 'chip' },
  { id: 'settings', component: 'settings', title: '设置', label: '设置', icon: 'gear' },
]

const regionToggles = [
  { id: 'explorer' as const, title: '折叠文件区', icon: 'layout-left' },
  { id: 'terminal' as const, title: '折叠终端区', icon: 'layout-bottom' },
  { id: 'agent' as const, title: '折叠对话区', icon: 'layout-right' },
]
</script>

<template>
  <div class="workbench">
    <header class="layout-header">
      <div class="layout-header-left">
        <div class="layout-brand">
          <span class="brand-mark">CA</span>
          <span>Code Agent</span>
        </div>
        <nav class="top-nav">
          <button
            v-for="item in items"
            :key="item.id"
            type="button"
            class="top-nav-link"
            :class="{ active: store.activity === item.id }"
            :title="item.label"
            @click="openPanel(item.id, item.component, item.title)"
          >
            <AppIcon :name="item.icon" :size="14" />
            <span>{{ item.label }}</span>
          </button>
        </nav>
      </div>
      <div class="layout-actions">
        <button
          v-for="item in regionToggles"
          :key="item.id"
          type="button"
          class="icon-btn"
          :class="{ active: regions[item.id] }"
          :title="item.title"
          @click="toggleRegion(item.id)"
        >
          <AppIcon :name="item.icon" :size="14" />
        </button>
        <span class="header-divider" />
        <button type="button" class="icon-btn" title="切换主题" @click="theme = toggleTheme()">
          <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="14" />
        </button>
        <span class="ws-name" :title="store.workspace?.root_path">{{ store.workspace?.name }}</span>
        <button type="button" class="btn" @click="workspaceOpen = true">
          <AppIcon name="folder" :size="13" />
          打开工作区
        </button>
      </div>
    </header>
    <div class="workbench-body">
      <div class="dock">
        <DockviewVue
          class="dockview-theme-light dockview-theme-codeagent"
          :components="components"
          :default-tab-component="PanelTab"
          @ready="onReady"
        />
      </div>
    </div>
    <WorkspaceSwitch v-if="workspaceOpen" @close="workspaceOpen = false" />
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
  </div>
</template>

<style scoped>
.workbench {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.workbench-body {
  flex: 1;
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
.ws-name {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
  font-size: 12px;
}
</style>
