<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'
import BrandMark from '@/components/BrandMark.vue'
import AppIcon from '@/components/AppIcon.vue'

defineProps<{
  collapsed: boolean
  theme: 'light' | 'dark'
  trajectoryOpen?: boolean
}>()

const emit = defineEmits<{
  toggleCollapse: []
  openPanel: [id: string, component: string, title: string]
  toggleTheme: []
  toggleTrajectory: []
  openTrajectoryDock: []
}>()

const store = useAppStore()

const navItems = [
  { id: 'agent', component: 'agent', title: 'Agent', label: '对话', icon: 'sparkles' },
  { id: 'trajectory', component: '', title: '', label: '轨迹', icon: 'clock', action: 'trajectory' as const },
  { id: 'explorer', component: 'explorer', title: '文件目录', label: '文件', icon: 'folder' },
  { id: 'editor', component: 'editor', title: '编辑器', label: '编辑器', icon: 'file' },
  { id: 'terminal', component: 'terminal', title: '终端', label: '终端', icon: 'terminal' },
  { id: 'ports', component: 'ports', title: '端口', label: '端口', icon: 'globe' },
  { id: 'git', component: 'git', title: 'Git', label: 'Git', icon: 'git' },
]

const footItems = [
  { id: 'skills', component: 'skills', title: 'Skill', label: 'Skill', icon: 'book' },
  { id: 'models', component: 'models', title: '模型', label: '模型', icon: 'chip' },
  { id: 'settings', component: 'settings', title: '设置', label: '设置', icon: 'sliders' },
]

const workspaceLabel = computed(() => store.workspace?.name || '工作空间')

async function startNewChat() {
  await store.newChat()
  emit('openPanel', 'agent', 'agent', 'Agent')
}

async function openHistory(id: string) {
  await store.openConversation(id)
  emit('openPanel', 'agent', 'agent', 'Agent')
}

async function removeConversation(id: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  await store.deleteConversation(id)
}

function open(id: string, component: string, title: string, action?: 'trajectory', e?: MouseEvent) {
  if (action === 'trajectory') {
    if (e?.altKey) {
      emit('openTrajectoryDock')
      return
    }
    emit('toggleTrajectory')
    return
  }
  emit('openPanel', id, component, title)
}
</script>

<template>
  <aside class="session-sidebar" :class="{ collapsed }" aria-label="会话与工作区">
    <div class="sidebar-brand">
      <BrandMark :size="collapsed ? 28 : 24" />
      <div v-if="!collapsed" class="brand-copy">
        <span class="brand-title">Code Agent</span>
        <span class="brand-ws" :title="store.workspace?.root_path">{{ workspaceLabel }}</span>
      </div>
      <button type="button" class="sidebar-icon-btn collapse-btn" :title="collapsed ? '展开侧栏' : '收起侧栏'" @click="emit('toggleCollapse')">
        <AppIcon :name="collapsed ? 'chevron-right' : 'panel-left'" :size="15" />
      </button>
    </div>

    <button type="button" class="new-session" :title="collapsed ? '新会话' : undefined" @click="startNewChat">
      <AppIcon name="plus" :size="16" />
      <span v-if="!collapsed">新会话</span>
    </button>

    <div v-if="!collapsed" class="session-list">
      <p class="session-list-label">会话</p>
      <div
        v-for="c in store.conversations"
        :key="c.id"
        class="session-item-wrap"
      >
        <button
          type="button"
          class="session-item"
          :class="{ active: c.id === store.conversationId }"
          @click="openHistory(c.id)"
        >
          <AppIcon name="chat" :size="14" />
          <span class="session-title">{{ c.title }}</span>
        </button>
        <button
          type="button"
          class="session-delete"
          title="删除会话"
          @click="removeConversation(c.id, $event)"
        >
          <AppIcon name="trash" :size="13" />
        </button>
      </div>
      <p v-if="!store.conversations.length" class="session-empty">暂无历史会话</p>
    </div>

    <nav class="sidebar-nav" aria-label="工作区面板">
      <button
        v-for="item in navItems"
        :key="item.id"
        type="button"
        class="sidebar-nav-item"
        :class="{ active: item.action === 'trajectory' ? (trajectoryOpen || store.activity === 'trajectory') : store.activity === item.id }"
        :title="item.action === 'trajectory' ? `${item.label}（Alt+点击弹出为面板）` : item.label"
        @click="open(item.id, item.component, item.title, item.action, $event)"
      >
        <AppIcon :name="item.icon" :size="18" />
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
        <AppIcon :name="item.icon" :size="17" />
        <span v-if="!collapsed">{{ item.label }}</span>
      </button>
      <button type="button" class="sidebar-nav-item" title="切换主题" @click="emit('toggleTheme')">
        <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
        <span v-if="!collapsed">{{ theme === 'dark' ? '浅色' : '深色' }}</span>
      </button>
      <button
        type="button"
        class="sidebar-nav-item"
        title="打开工作空间"
        @click="open('workspace', 'workspace', '工作空间')"
      >
        <AppIcon name="home" :size="16" />
        <span v-if="!collapsed">工作空间</span>
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
.sidebar-icon-btn {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.sidebar-icon-btn:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.new-session {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0 10px 10px;
  height: 36px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text-h);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.collapsed .new-session {
  width: 36px;
  margin: 0 auto 10px;
  padding: 0;
}
.new-session:hover {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  background: var(--primary-soft);
  color: var(--primary);
}
.session-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 8px 8px;
}
.session-list-label {
  margin: 0 0 6px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.session-item-wrap {
  position: relative;
  display: flex;
  align-items: stretch;
}
.session-item-wrap:hover .session-delete {
  opacity: 1;
}
.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 34px 8px 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.session-delete {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
}
.session-delete:hover {
  background: color-mix(in srgb, var(--danger) 12%, var(--code-bg));
  color: var(--danger);
}
.session-item-wrap:focus-within .session-delete {
  opacity: 1;
}
.session-item:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.session-item.active {
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 600;
}
.session-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-empty {
  margin: 8px;
  font-size: 12px;
  color: var(--text-muted);
}
.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
  border-top: var(--border-width) solid var(--border);
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
  min-height: 36px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
}
.collapsed .sidebar-nav-item {
  justify-content: center;
  padding: 0;
  width: 36px;
  margin: 0 auto;
}
.sidebar-nav-item:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.sidebar-nav-item.active {
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 600;
}
</style>
