<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
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
const mode = defineModel<'commands' | 'files'>('mode', { default: 'commands' })

const emit = defineEmits<{
  openPanel: [id: string, component: string, title: string]
  toggleTheme: []
}>()

const { t } = useI18n()
const store = useAppStore()
const query = ref('')
const active = ref(0)
const inputEl = ref<HTMLInputElement | null>(null)
const fileHits = ref<{ path: string; name: string }[]>([])
const fileLoading = ref(false)
let fileSearchTimer: ReturnType<typeof setTimeout> | null = null
let fileSearchGen = 0
const shortcut = paletteShortcutLabel()
const altShortcut = isMacMod() ? '⌘K' : 'Ctrl+K'
const fileShortcut = isMacMod() ? '⌘P' : 'Ctrl+P'

const staticCommands = computed<PaletteItem[]>(() => [
  {
    id: 'new-chat',
    title: t('commandPalette.newChat'),
    icon: 'plus',
    group: t('commandPalette.groupSession'),
    keywords: 'new chat',
    run: async () => {
      await store.newChat()
      emit('openPanel', 'agent', 'agent', t('panels.agent'))
    },
  },
  { id: 'agent', title: t('commandPalette.openAgent'), icon: 'atom', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'agent', 'agent', t('panels.agent')) },
  { id: 'trajectory', title: t('commandPalette.openTrajectory'), icon: 'clock', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'trajectory', 'trajectory', t('panels.trajectory')) },
  { id: 'explorer', title: t('commandPalette.openExplorer'), icon: 'folder', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'explorer', 'explorer', t('panels.explorer')) },
  { id: 'search', title: t('commandPalette.openSearch'), icon: 'search', group: t('commandPalette.groupPanel'), keywords: 'find replace grep', run: () => store.openSearch() },
  { id: 'editor', title: t('commandPalette.openEditor'), icon: 'file', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'editor', 'editor', t('panels.editor')) },
  { id: 'terminal', title: t('commandPalette.openTerminal'), icon: 'terminal', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'terminal', 'terminal', t('panels.terminal')) },
  { id: 'ports', title: t('commandPalette.openPorts'), icon: 'ports', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'ports', 'ports', t('panels.ports')) },
  { id: 'git', title: t('commandPalette.openGit'), icon: 'git', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'git', 'git', t('panels.git')) },
  { id: 'skills', title: t('commandPalette.openSkills'), icon: 'book', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'skills', 'skills', t('panels.skills')) },
  { id: 'plugins', title: t('commandPalette.openPlugins'), icon: 'puzzle', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'plugins', 'plugins', t('panels.plugins')) },
  { id: 'models', title: t('commandPalette.openModels'), icon: 'chip', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'models', 'models', t('panels.models')) },
  { id: 'settings', title: t('commandPalette.openSettings'), icon: 'sliders', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'settings', 'settings', t('panels.settings')) },
  { id: 'workspace', title: t('commandPalette.openWorkspace'), icon: 'home', group: t('commandPalette.groupPanel'), run: () => emit('openPanel', 'workspace', 'workspace', t('panels.workspace')) },
  {
    id: 'inline-edit',
    title: t('commandPalette.inlineEdit'),
    icon: 'sparkles',
    group: t('commandPalette.groupEditor'),
    keywords: 'inline edit cmd k ctrl k rewrite',
    run: () => {
      emit('openPanel', 'editor', 'editor', t('panels.editor'))
      window.dispatchEvent(new Event('ca-focus-editor'))
      window.dispatchEvent(new Event('ca-inline-edit'))
    },
  },
  {
    id: 'goto-definition',
    title: t('commandPalette.gotoDefinition'),
    icon: 'search',
    group: t('commandPalette.groupEditor'),
    keywords: 'go to definition f12 symbol jump',
    run: () => {
      emit('openPanel', 'editor', 'editor', t('panels.editor'))
      window.dispatchEvent(new Event('ca-focus-editor'))
      window.dispatchEvent(new Event('ca-goto-definition'))
    },
  },
  { id: 'toggle-theme', title: t('commandPalette.toggleTheme'), icon: 'sun', group: t('commandPalette.groupLayout'), keywords: 'dark light', run: () => emit('toggleTheme') },
])

const sessionCommands = computed<PaletteItem[]>(() =>
  store.conversations.map((c) => ({
    id: `chat:${c.id}`,
    title: c.title,
    subtitle: formatRelativeTime(c.updated_at || c.created_at),
    icon: 'chat',
    group: t('commandPalette.groupSession'),
    run: async () => {
      await store.openConversation(c.id)
      emit('openPanel', 'agent', 'agent', t('panels.agent'))
    },
  })),
)

const commandItems = computed(() => {
  const q = query.value.trim().toLowerCase()
  const sessions = q ? sessionCommands.value : sessionCommands.value.slice(0, 6)
  const all = [...staticCommands.value, ...sessions]
  if (!q) return all
  return all.filter((item) => {
    const hay = `${item.title} ${item.subtitle || ''} ${item.group} ${item.keywords || ''}`.toLowerCase()
    return hay.includes(q)
  })
})

const fileItems = computed<PaletteItem[]>(() =>
  fileHits.value.map((f) => ({
    id: `file:${f.path}`,
    title: f.name,
    subtitle: f.path,
    icon: 'file',
    group: t('commandPalette.groupFiles'),
    run: async () => {
      await store.openPath(f.path, false)
      emit('openPanel', 'editor', 'editor', t('panels.editor'))
    },
  })),
)

const items = computed(() => (mode.value === 'files' ? fileItems.value : commandItems.value))

const grouped = computed(() => {
  const order =
    mode.value === 'files'
      ? [t('commandPalette.groupFiles')]
      : [t('commandPalette.groupSession'), t('commandPalette.groupPanel'), t('commandPalette.groupLayout')]
  const map = new Map<string, PaletteItem[]>()
  for (const item of items.value) {
    const list = map.get(item.group) || []
    list.push(item)
    map.set(item.group, list)
  }
  return order.filter((g) => map.has(g)).map((g) => ({ group: g, items: map.get(g)! }))
})

const flat = computed(() => grouped.value.flatMap((g) => g.items))

async function searchFiles(q: string) {
  if (!store.workspaceId) {
    fileHits.value = []
    return
  }
  const gen = ++fileSearchGen
  fileLoading.value = true
  try {
    const params = new URLSearchParams({ q, limit: '40' })
    const data = await api<{ files: { path: string; name: string }[] }>(
      `/api/workspaces/${store.workspaceId}/find-files?${params}`,
    )
    if (gen !== fileSearchGen) return
    fileHits.value = data.files || []
  } catch {
    if (gen !== fileSearchGen) return
    fileHits.value = []
  } finally {
    if (gen === fileSearchGen) fileLoading.value = false
  }
}

function scheduleFileSearch() {
  if (fileSearchTimer) clearTimeout(fileSearchTimer)
  fileSearchTimer = setTimeout(() => {
    fileSearchTimer = null
    void searchFiles(query.value.trim())
  }, 120)
}

watch(open, async (value) => {
  query.value = ''
  active.value = 0
  if (value) {
    if (mode.value === 'files') void searchFiles('')
    await nextTick()
    inputEl.value?.focus()
  } else {
    mode.value = 'commands'
    fileHits.value = []
  }
})

watch(mode, (value) => {
  if (!open.value) return
  query.value = ''
  active.value = 0
  if (value === 'files') void searchFiles('')
})

watch(query, () => {
  if (mode.value === 'files') scheduleFileSearch()
})

watch(items, () => {
  active.value = 0
})

watch(active, async () => {
  await nextTick()
  document.querySelector('.palette-item.active')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
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
  // Ctrl/Cmd+Shift+P always; Ctrl/Cmd+K outside the editor (editor uses Ctrl/Cmd+K for inline edit)
  const palette = (key === 'p' && e.shiftKey) || (key === 'k' && !e.shiftKey && !inEditor)
  if (!palette) return
  e.preventDefault()
  e.stopPropagation()
  if (open.value && mode.value === 'commands') {
    open.value = false
    return
  }
  mode.value = 'commands'
  open.value = true
}

onMounted(() => {
  window.addEventListener('keydown', onWindowKey, true)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onWindowKey, true)
  if (fileSearchTimer) clearTimeout(fileSearchTimer)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="palette-root" @keydown="onKey">
      <div class="palette-backdrop" @click="close" />
      <div
        class="palette"
        role="dialog"
        aria-modal="true"
        :aria-label="mode === 'files' ? t('commandPalette.ariaFiles') : t('commandPalette.aria')"
      >
        <div class="palette-search">
          <AppIcon :name="mode === 'files' ? 'file' : 'search'" :size="16" />
          <input
            ref="inputEl"
            v-model="query"
            type="search"
            :placeholder="mode === 'files' ? t('commandPalette.placeholderFiles') : t('commandPalette.placeholder')"
            autocomplete="off"
            spellcheck="false"
          />
          <kbd>{{ mode === 'files' ? fileShortcut : shortcut }}</kbd>
        </div>
        <div class="palette-list" role="listbox">
          <p v-if="mode === 'files' && fileLoading && !flat.length" class="palette-empty">{{ t('commandPalette.loadingFiles') }}</p>
          <p v-else-if="!flat.length" class="palette-empty">
            {{ mode === 'files' ? t('commandPalette.emptyFiles') : t('commandPalette.empty') }}
          </p>
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
          <span>{{ t('commandPalette.hint') }}</span>
          <span v-if="mode === 'files'">{{ fileShortcut }}</span>
          <span v-else>{{ shortcut }} {{ t('commandPalette.or') }} {{ altShortcut }}</span>
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
  gap: 8px;
  width: 100%;
  min-height: 34px;
  padding: 4px 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-h);
  font-size: 13px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.12s ease;
}
.palette-item:hover,
.palette-item.active {
  background: var(--code-bg);
  color: var(--text-h);
}
.palette-item.active {
  font-weight: 500;
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
  color: var(--text-muted);
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
