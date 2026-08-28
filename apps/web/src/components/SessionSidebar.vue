<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import BrandMark from '@/components/BrandMark.vue'
import AppIcon from '@/components/AppIcon.vue'

defineProps<{
  collapsed: boolean
  theme: 'light' | 'dark'
}>()

const emit = defineEmits<{
  toggleCollapse: []
  openPanel: [id: string, component: string, title: string]
  toggleTheme: []
}>()

const { t } = useI18n()
const store = useAppStore()

const navItems = computed(() => [
  { id: 'agent', component: 'agent', title: t('panels.agent'), label: t('sidebar.chat'), icon: 'atom' },
  { id: 'trajectory', component: 'trajectory', title: t('panels.trajectory'), label: t('sidebar.trajectory'), icon: 'clock' },
  { id: 'explorer', component: 'explorer', title: t('panels.explorer'), label: t('sidebar.files'), icon: 'folder' },
  { id: 'search', component: 'search', title: t('panels.search'), label: t('panels.search'), icon: 'search' },
  { id: 'editor', component: 'editor', title: t('panels.editor'), label: t('panels.editor'), icon: 'file' },
  { id: 'terminal', component: 'terminal', title: t('panels.terminal'), label: t('panels.terminal'), icon: 'terminal' },
  { id: 'ports', component: 'ports', title: t('panels.ports'), label: t('panels.ports'), icon: 'ports' },
  { id: 'git', component: 'git', title: t('panels.git'), label: t('panels.git'), icon: 'git' },
])

const footItems = computed(() => [
  { id: 'skills', component: 'skills', title: t('panels.skills'), label: t('panels.skills'), icon: 'book' },
  { id: 'memory', component: 'memory', title: t('panels.memory'), label: t('panels.memory'), icon: 'memory' },
  { id: 'plugins', component: 'plugins', title: t('panels.plugins'), label: t('panels.plugins'), icon: 'puzzle' },
  { id: 'models', component: 'models', title: t('panels.models'), label: t('panels.models'), icon: 'chip' },
  { id: 'settings', component: 'settings', title: t('panels.settings'), label: t('panels.settings'), icon: 'sliders' },
])

const workspaceLabel = computed(() => store.workspace?.name || t('panels.workspace'))

function open(id: string, component: string, title: string) {
  if (id === 'search') {
    store.openSearch()
    return
  }
  emit('openPanel', id, component, title)
}
</script>

<template>
  <aside class="session-sidebar" :class="{ collapsed }" :aria-label="t('sidebar.aria')">
    <div class="sidebar-brand">
      <BrandMark :size="collapsed ? 28 : 24" />
      <div v-if="!collapsed" class="brand-copy">
        <span class="brand-title">Code Agent</span>
        <span class="brand-ws" :title="store.workspace?.root_path">{{ workspaceLabel }}</span>
      </div>
      <button type="button" class="ghost-icon-btn collapse-btn" :title="collapsed ? t('sidebar.expand') : t('sidebar.collapse')" @click="emit('toggleCollapse')">
        <AppIcon :name="collapsed ? 'chevron-right' : 'panel-left'" :size="16" :stroke-width="1.75" />
      </button>
    </div>

    <nav class="sidebar-nav" :aria-label="t('sidebar.nav')">
      <button
        v-for="item in navItems"
        :key="item.id"
        type="button"
        class="sidebar-nav-item"
        :class="{ active: store.activity === item.id }"
        :title="item.label"
        @click="open(item.id, item.component, item.title)"
      >
        <AppIcon :name="item.icon" :size="16" :stroke-width="1.75" />
        <span v-if="!collapsed">{{ item.label }}</span>
      </button>
    </nav>

    <div class="sidebar-foot">
      <button
        v-for="item in footItems"
        :key="item.id"
        type="button"
        class="sidebar-nav-item"
        :class="{ active: store.activity === item.id }"
        :title="item.label"
        @click="open(item.id, item.component, item.title)"
      >
        <AppIcon :name="item.icon" :size="16" :stroke-width="1.75" />
        <span v-if="!collapsed">{{ item.label }}</span>
      </button>
      <button type="button" class="sidebar-nav-item" :title="t('theme.toggle')" @click="emit('toggleTheme')">
        <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" :stroke-width="1.75" />
        <span v-if="!collapsed">{{ theme === 'dark' ? t('theme.light') : t('theme.dark') }}</span>
      </button>
      <button
        type="button"
        class="sidebar-nav-item"
        :title="t('sidebar.openWorkspace')"
        @click="open('workspace', 'workspace', t('panels.workspace'))"
      >
        <AppIcon name="home" :size="16" :stroke-width="1.75" />
        <span v-if="!collapsed">{{ t('sidebar.workspace') }}</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.session-sidebar {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--sidebar-bg);
  border-right: var(--border-width) solid var(--border);
}
.session-sidebar.collapsed {
  width: var(--sidebar-rail-w) !important;
}
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 10px 8px;
  min-height: 52px;
}
.collapsed .sidebar-brand {
  flex-direction: column;
  gap: 8px;
  padding: 10px 0 6px;
}
.brand-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.brand-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-h);
  letter-spacing: -0.02em;
}
.brand-ws {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.collapse-btn {
  margin-left: auto;
}
.collapsed .collapse-btn {
  margin-left: 0;
}
.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.sidebar-foot {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
  border-top: var(--border-width) solid var(--border);
}
.sidebar-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 34px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.12s ease, color 0.12s ease;
}
.collapsed .sidebar-nav-item {
  justify-content: center;
  padding: 0;
  width: var(--ghost-btn-height);
  margin: 0 auto;
}
.sidebar-nav-item:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.sidebar-nav-item.active {
  background: var(--code-bg);
  color: var(--primary);
  font-weight: 500;
}
</style>
