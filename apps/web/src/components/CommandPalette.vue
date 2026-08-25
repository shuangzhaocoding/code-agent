<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { useAppStore } from '@/stores/app'
import { formatRelativeTime, isMacMod, paletteShortcutLabel } from '@/utils/relativeTime'

type PaletteItem = {
  id: string
  title: string
  subtitle?: string
  icon: string
  group: string
  keywords?: string
  run: () => void | Promise<void>
}

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  openPanel: [id: string, component: string, title: string]
  toggleTheme: []
  toggleSidebar: []
  toggleTrajectory: []
  openTrajectoryDock: []
}>()

const store = useAppStore()
const query = ref('')
const active = ref(0)
const inputEl = ref<HTMLInputElement | null>(null)
const shortcut = paletteShortcutLabel()
const altShortcut = isMacMod() ? '⌘K' : 'Ctrl+K'

const staticCommands = computed<PaletteItem[]>(() => [
  {
    id: 'new-chat',
    title: '新会话',
    icon: 'plus',
    group: '会话',
    keywords: 'new chat',
    run: async () => {
      await store.newChat()
      emit('openPanel', 'agent', 'agent', 'Agent')
    },
  },
  { id: 'agent', title: '打开对话', icon: 'atom', group: '面板', run: () => emit('openPanel', 'agent', 'agent', 'Agent') },
  { id: 'explorer', title: '打开文件目录', icon: 'folder', group: '面板', run: () => emit('openPanel', 'explorer', 'explorer', '文件目录') },
  { id: 'search', title: '打开搜索', icon: 'search', group: '面板', keywords: 'find replace grep', run: () => store.openSearch() },
  { id: 'editor', title: '打开编辑器', icon: 'file', group: '面板', run: () => emit('openPanel', 'editor', 'editor', '编辑器') },
  { id: 'terminal', title: '打开终端', icon: 'terminal', group: '面板', run: () => emit('openPanel', 'terminal', 'terminal', '终端') },
  { id: 'ports', title: '打开端口', icon: 'ports', group: '面板', run: () => emit('openPanel', 'ports', 'ports', '端口') },
  { id: 'git', title: '打开 Git', icon: 'git', group: '面板', run: () => emit('openPanel', 'git', 'git', 'Git') },
  { id: 'skills', title: '打开 Skill', icon: 'book', group: '面板', run: () => emit('openPanel', 'skills', 'skills', 'Skill') },
  { id: 'plugins', title: '打开插件', icon: 'puzzle', group: '面板', run: () => emit('openPanel', 'plugins', 'plugins', '插件') },
  { id: 'models', title: '打开模型', icon: 'chip', group: '面板', run: () => emit('openPanel', 'models', 'models', '模型') },
  { id: 'settings', title: '打开设置', icon: 'sliders', group: '面板', run: () => emit('openPanel', 'settings', 'settings', '设置') },
  { id: 'workspace', title: '打开工作空间', icon: 'home', group: '面板', run: () => emit('openPanel', 'workspace', 'workspace', '工作空间') },
  { id: 'toggle-sidebar', title: '切换侧栏', icon: 'panel-left', group: '布局', run: () => emit('toggleSidebar') },
  { id: 'toggle-trajectory', title: '切换轨迹', icon: 'clock', group: '布局', run: () => emit('toggleTrajectory') },
  { id: 'popout-trajectory', title: '弹出轨迹面板', icon: 'clock', group: '布局', keywords: 'dock', run: () => emit('openTrajectoryDock') },
  { id: 'toggle-theme', title: '切换主题', icon: 'sun', group: '布局', keywords: 'dark light', run: () => emit('toggleTheme') },
])

const sessionCommands = computed<PaletteItem[]>(() =>
  store.conversations.map((c) => ({
    id: `chat:${c.id}`,
    title: c.title,
    subtitle: formatRelativeTime(c.updated_at || c.created_at),
    icon: 'chat',
    group: '会话',
    run: async () => {
      await store.openConversation(c.id)
      emit('openPanel', 'agent', 'agent', 'Agent')
    },
  })),
)

const items = computed(() => {
  const q = query.value.trim().toLowerCase()
  const sessions = q ? sessionCommands.value : sessionCommands.value.slice(0, 6)
  const all = [...staticCommands.value, ...sessions]
  if (!q) return all
  return all.filter((item) => {
    const hay = `${item.title} ${item.subtitle || ''} ${item.group} ${item.keywords || ''}`.toLowerCase()
    return hay.includes(q)
  })
})

const grouped = computed(() => {
  const order = ['会话', '面板', '布局']
  const map = new Map<string, PaletteItem[]>()
  for (const item of items.value) {
    const list = map.get(item.group) || []
    list.push(item)
    map.set(item.group, list)
  }
  return order.filter((g) => map.has(g)).map((g) => ({ group: g, items: map.get(g)! }))
})

const flat = computed(() => grouped.value.flatMap((g) => g.items))

watch(open, async (value) => {
  query.value = ''
  active.value = 0
  if (value) {
    await nextTick()
    inputEl.value?.focus()
  }
})

watch(items, () => {
  active.value = 0
})

watch(active, async () => {
  await nextTick()
  document.querySelector('.palette-item.active')?.scrollIntoView({ block: 'nearest' })
})

function close() {
  open.value = false
}

async function run(item: PaletteItem) {
  close()
  await item.run()
}

function onKey(e: KeyboardEvent) {
  if (!open.value) return
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    active.value = Math.min(flat.value.length - 1, active.value + 1)
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    active.value = Math.max(0, active.value - 1)
    return
  }
  if (e.key === 'Enter') {
    const item = flat.value[active.value]
    if (item) {
      e.preventDefault()
      void run(item)
    }
  }
}

function onWindowKey(e: KeyboardEvent) {
  if (e.isComposing || e.repeat) return
  const mod = e.metaKey || e.ctrlKey
  if (!mod) return
  const key = e.key.toLowerCase()
  const inEditor = e.target instanceof Element && !!e.target.closest('.monaco-editor, .xterm, .xterm-helper-textarea')
  const palette = (key === 'p' && e.shiftKey) || (key === 'k' && !e.shiftKey && !inEditor)
  if (!palette) return
  e.preventDefault()
  e.stopPropagation()
  open.value = !open.value
}

onMounted(() => {
  window.addEventListener('keydown', onWindowKey, true)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onWindowKey, true)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="palette-root" @keydown="onKey">
      <div class="palette-backdrop" @click="close" />
      <div class="palette" role="dialog" aria-modal="true" aria-label="命令面板">
        <div class="palette-search">
          <AppIcon name="search" :size="16" />
          <input
            ref="inputEl"
            v-model="query"
            type="search"
            placeholder="搜索命令或会话…"
            autocomplete="off"
            spellcheck="false"
          />
          <kbd>{{ shortcut }}</kbd>
        </div>
        <div class="palette-list" role="listbox">
          <p v-if="!flat.length" class="palette-empty">没有匹配的命令</p>
          <section v-for="section in grouped" :key="section.group">
            <h2>{{ section.group }}</h2>
            <button
              v-for="item in section.items"
              :key="item.id"
              type="button"
              class="palette-item"
              :class="{ active: flat[active]?.id === item.id }"
              role="option"
              :aria-selected="flat[active]?.id === item.id"
              @mouseenter="active = flat.findIndex((row) => row.id === item.id)"
              @click="run(item)"
            >
              <AppIcon :name="item.icon" :size="15" />
              <span class="palette-copy">
                <span>{{ item.title }}</span>
                <small v-if="item.subtitle">{{ item.subtitle }}</small>
              </span>
            </button>
          </section>
        </div>
        <footer class="palette-foot">
          <span>↑↓ 选择 · Enter 执行 · Esc 关闭</span>
          <span>{{ shortcut }} 或 {{ altShortcut }}</span>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.palette-root {
  position: fixed;
  inset: 0;
  z-index: 24000;
}
.palette-backdrop {
  position: absolute;
  inset: 0;
  background: color-mix(in srgb, var(--page-bg) 55%, transparent);
}
.palette {
  position: relative;
  width: min(560px, calc(100vw - 32px));
  margin: 12vh auto 0;
  background: var(--panel-bg);
  border: var(--border-width) solid var(--border-strong);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.palette-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: var(--border-width) solid var(--border);
  color: var(--text-muted);
}
.palette-search input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-h);
  outline: none;
  font-size: 14px;
}
.palette-search kbd {
  flex-shrink: 0;
  font-family: var(--mono);
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  border: var(--border-width) solid var(--border);
  background: var(--code-bg);
  color: var(--text-secondary);
}
.palette-list {
  max-height: min(420px, 56vh);
  overflow: auto;
  padding: 8px;
}
.palette-list h2 {
  margin: 8px 8px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.palette-list section:first-child h2 {
  margin-top: 0;
}
.palette-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-h);
  text-align: left;
  cursor: pointer;
}
.palette-item.active {
  background: var(--primary-soft);
  color: var(--primary);
}
.palette-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.palette-copy span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.palette-copy small {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 400;
}
.palette-item.active .palette-copy small {
  color: color-mix(in srgb, var(--primary) 70%, var(--text-muted));
}
.palette-empty {
  margin: 24px 8px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}
.palette-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  border-top: var(--border-width) solid var(--border);
  font-size: 11px;
  color: var(--text-muted);
}
</style>
