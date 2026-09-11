<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon, { type AppIconName } from '@/components/AppIcon.vue'
import BrandMark from '@/components/BrandMark.vue'
import { useToast } from '@/composables/useToast'
import { useAppStore } from '@/stores/app'
import {
  MENU_BAR_POSITIONS,
  setMenuBarPosition,
  type MenuBarPosition,
} from '@/utils/layoutPrefs'
import { isMacMod, paletteShortcutLabel } from '@/utils/relativeTime'

type MenuId = 'file' | 'edit' | 'panel' | 'help'

type MenuItem = {
  id: string
  label: string
  icon?: AppIconName | string
  shortcut?: string
  disabled?: boolean
  separator?: boolean
  checked?: boolean
  run?: () => void | Promise<void>
}

const props = defineProps<{
  theme: 'light' | 'dark'
  position: MenuBarPosition
  /** Embed into Electron custom title bar (drag region + control insets). */
  asTitleBar?: boolean
  /** Hide brand when a DesktopTitleBar already shows it. */
  hideBrand?: boolean
}>()

const emit = defineEmits<{
  openPanel: [id: string, component: string, title: string]
  toggleTheme: []
  openCommandPalette: []
  openFilePalette: []
}>()

const { t } = useI18n()
const store = useAppStore()
const toast = useToast()
const openMenu = ref<MenuId | null>(null)
const rootEl = ref<HTMLElement | null>(null)
const dropdownEl = ref<HTMLElement | null>(null)
const importInput = ref<HTMLInputElement | null>(null)
const dropdownStyle = ref<Record<string, string>>({})

const modKey = isMacMod() ? '⌘' : 'Ctrl+'
const commandShortcut = paletteShortcutLabel()
const fileShortcut = isMacMod() ? '⌘P' : 'Ctrl+P'
const searchShortcut = isMacMod() ? '⌘⇧F' : 'Ctrl+Shift+F'
const saveShortcut = `${modKey}S`
const newChatShortcut = `${modKey}N`

const canSave = computed(() => {
  const file = store.openFile
  return Boolean(file && !file.readonly)
})

const isSideRail = computed(() => props.position === 'left' || props.position === 'right')

const PANEL_ICONS: Record<string, AppIconName> = {
  agent: 'atom',
  trajectory: 'clock',
  explorer: 'folder',
  search: 'search',
  editor: 'file',
  terminal: 'terminal',
  ports: 'ports',
  git: 'git',
  skills: 'book',
  memory: 'memory',
  plugins: 'puzzle',
  models: 'chip',
  settings: 'sliders',
}

const POSITION_ICONS: Record<MenuBarPosition, AppIconName> = {
  top: 'menu',
  left: 'layout-left',
  right: 'layout-right',
  bottom: 'layout-bottom',
}

function closeMenu() {
  openMenu.value = null
}

function placeDropdown(trigger: HTMLElement) {
  const rect = trigger.getBoundingClientRect()
  const gap = 6
  if (props.position === 'top') {
    dropdownStyle.value = {
      top: `${Math.round(rect.bottom + gap)}px`,
      left: `${Math.round(rect.left)}px`,
    }
    return
  }
  if (props.position === 'bottom') {
    dropdownStyle.value = {
      bottom: `${Math.round(window.innerHeight - rect.top + gap)}px`,
      left: `${Math.round(rect.left)}px`,
    }
    return
  }
  if (props.position === 'left') {
    dropdownStyle.value = {
      top: `${Math.round(rect.top)}px`,
      left: `${Math.round(rect.right + gap)}px`,
    }
    return
  }
  dropdownStyle.value = {
    top: `${Math.round(rect.top)}px`,
    right: `${Math.round(window.innerWidth - rect.left + gap)}px`,
  }
}

async function toggleMenu(id: MenuId, e: MouseEvent) {
  if (openMenu.value === id) {
    closeMenu()
    return
  }
  openMenu.value = id
  const trigger = e.currentTarget as HTMLElement
  await nextTick()
  placeDropdown(trigger)
  requestAnimationFrame(() => placeDropdown(trigger))
}

function onMenuEnter(id: MenuId, e: MouseEvent) {
  if (!openMenu.value || openMenu.value === id) return
  openMenu.value = id
  const trigger = e.currentTarget as HTMLElement
  void nextTick(() => placeDropdown(trigger))
}

async function runItem(item: MenuItem) {
  if (item.disabled || item.separator || !item.run) return
  closeMenu()
  await item.run()
}

function openPanel(id: string, component: string) {
  emit('openPanel', id, component, t(`panels.${id}`))
}

function setPosition(position: MenuBarPosition) {
  if (position === props.position) return
  setMenuBarPosition(position)
}

const menus = computed(() => {
  const fileItems: MenuItem[] = [
    {
      id: 'workspace',
      label: t('menu.items.openWorkspace'),
      icon: 'home',
      run: () => openPanel('workspace', 'workspace'),
    },
    {
      id: 'new-chat',
      label: t('menu.items.newChat'),
      icon: 'chat-plus',
      shortcut: newChatShortcut,
      run: async () => {
        await store.newChat()
        openPanel('agent', 'agent')
        window.dispatchEvent(new Event('ca-focus-composer'))
      },
    },
    {
      id: 'open-file',
      label: t('menu.items.openFile'),
      icon: 'file',
      shortcut: fileShortcut,
      run: () => emit('openFilePalette'),
    },
    {
      id: 'save',
      label: t('menu.items.save'),
      icon: 'save',
      shortcut: saveShortcut,
      disabled: !canSave.value,
      run: async () => {
        await store.saveOpenFile()
        toast.success(t('common.saved'))
      },
    },
    { id: 'sep-file', label: '', separator: true },
    {
      id: 'layout-export',
      label: t('menu.items.exportLayout'),
      icon: 'download',
      run: () => window.dispatchEvent(new Event('ca-layout-export')),
    },
    {
      id: 'layout-import',
      label: t('menu.items.importLayout'),
      icon: 'upload',
      run: () => importInput.value?.click(),
    },
  ]

  const editItems: MenuItem[] = [
    {
      id: 'commands',
      label: t('menu.items.commandPalette'),
      icon: 'command',
      shortcut: commandShortcut,
      run: () => emit('openCommandPalette'),
    },
    {
      id: 'search',
      label: t('menu.items.search'),
      icon: 'search',
      shortcut: searchShortcut,
      run: () => store.openSearch(),
    },
    { id: 'sep-edit', label: '', separator: true },
    {
      id: 'theme',
      label: props.theme === 'dark' ? t('theme.light') : t('theme.dark'),
      icon: props.theme === 'dark' ? 'sun' : 'moon',
      run: () => emit('toggleTheme'),
    },
    { id: 'sep-pos', label: '', separator: true },
    ...MENU_BAR_POSITIONS.map((position) => ({
      id: `pos-${position}`,
      label: t(`menu.positions.${position}`),
      icon: POSITION_ICONS[position],
      checked: props.position === position,
      run: () => setPosition(position),
    })),
  ]

  const PANEL_GROUPS: string[][] = [
    ['agent', 'trajectory'],
    ['explorer', 'search', 'editor', 'terminal'],
    ['ports', 'git'],
    ['skills', 'memory', 'plugins', 'models', 'settings'],
  ]

  const panelItems: MenuItem[] = []
  PANEL_GROUPS.forEach((group, groupIdx) => {
    if (groupIdx > 0) panelItems.push({ id: `sep-panel-${groupIdx}`, label: '', separator: true })
    for (const id of group) {
      panelItems.push({
        id: `panel-${id}`,
        label: t(`panels.${id}`),
        icon: PANEL_ICONS[id],
        run: () => {
          if (id === 'search') {
            store.openSearch()
            return
          }
          openPanel(id, id)
        },
      })
    }
  })

  const helpItems: MenuItem[] = [
    {
      id: 'shortcuts',
      label: t('menu.items.keyboardShortcuts'),
      icon: 'command',
      shortcut: commandShortcut,
      run: () => emit('openCommandPalette'),
    },
    {
      id: 'about',
      label: t('menu.items.about'),
      icon: 'help',
      run: () => {
        toast.info(t('menu.aboutBody', { name: 'Code Agent', version: '1.0.2' }))
      },
    },
  ]

  return [
    { id: 'file' as const, label: t('menu.file'), icon: 'file' as const, items: fileItems },
    { id: 'edit' as const, label: t('menu.edit'), icon: 'edit' as const, items: editItems },
    { id: 'panel' as const, label: t('menu.panel'), icon: 'layout-left' as const, items: panelItems },
    { id: 'help' as const, label: t('menu.help'), icon: 'help' as const, items: helpItems },
  ]
})

const activeMenu = computed(() => menus.value.find((menu) => menu.id === openMenu.value) || null)

function onImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    try {
      const parsed = JSON.parse(String(reader.result || ''))
      const onResult = (ev: Event) => {
        window.removeEventListener('ca-layout-import-result', onResult)
        const ok = Boolean((ev as CustomEvent<{ ok?: boolean }>).detail?.ok)
        if (ok) toast.success(t('layout.importDone'))
        else toast.error(t('layout.importInvalid'))
      }
      window.addEventListener('ca-layout-import-result', onResult)
      window.dispatchEvent(new CustomEvent('ca-layout-import', { detail: { layout: parsed } }))
    } catch {
      toast.error(t('layout.importInvalid'))
    }
  }
  reader.readAsText(file)
}

function onPointerDown(e: PointerEvent) {
  if (!openMenu.value) return
  const target = e.target as Node | null
  if (rootEl.value?.contains(target) || dropdownEl.value?.contains(target)) return
  closeMenu()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && openMenu.value) {
    e.stopPropagation()
    closeMenu()
  }
}

function onWindowResize() {
  if (!openMenu.value) return
  const trigger = rootEl.value?.querySelector('.menu-item.open .menu-trigger') as HTMLElement | null
  if (trigger) placeDropdown(trigger)
}

onMounted(() => {
  window.addEventListener('pointerdown', onPointerDown, true)
  window.addEventListener('keydown', onKeydown, true)
  window.addEventListener('resize', onWindowResize)
})
onUnmounted(() => {
  window.removeEventListener('pointerdown', onPointerDown, true)
  window.removeEventListener('keydown', onKeydown, true)
  window.removeEventListener('resize', onWindowResize)
})
</script>

<template>
  <header
    ref="rootEl"
    class="app-menu-bar"
    :class="[`pos-${position}`, { 'is-titlebar': asTitleBar }]"
    :aria-label="t('menu.aria')"
  >
    <div v-if="!hideBrand" class="menu-brand" title="Code Agent">
      <BrandMark :size="isSideRail ? 24 : 20" />
      <span v-if="!isSideRail" class="brand-title">Code Agent</span>
    </div>

    <nav class="menu-nav">
      <div
        v-for="menu in menus"
        :key="menu.id"
        class="menu-item"
        :class="{ open: openMenu === menu.id }"
      >
        <button
          type="button"
          class="menu-trigger"
          :aria-expanded="openMenu === menu.id"
          :aria-haspopup="true"
          :title="menu.label"
          @click="toggleMenu(menu.id, $event)"
          @mouseenter="onMenuEnter(menu.id, $event)"
        >
          <AppIcon :name="menu.icon" :size="14" :stroke-width="1.75" />
          <span class="menu-trigger-label">{{ menu.label }}</span>
        </button>
      </div>
    </nav>

    <div class="menu-actions">
      <button
        type="button"
        class="ghost-icon-btn"
        :title="t('menu.items.commandPalette')"
        @click="emit('openCommandPalette')"
      >
        <AppIcon name="search" :size="15" :stroke-width="1.75" />
      </button>
      <button
        type="button"
        class="ghost-icon-btn"
        :title="t('theme.toggle')"
        @click="emit('toggleTheme')"
      >
        <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="15" :stroke-width="1.75" />
      </button>
    </div>

    <input
      ref="importInput"
      type="file"
      accept="application/json,.json"
      hidden
      @change="onImportFile"
    />
  </header>

  <Teleport to="body">
    <div
      v-if="activeMenu"
      ref="dropdownEl"
      class="menu-dropdown"
      role="menu"
      :style="dropdownStyle"
    >
      <template v-for="item in activeMenu.items" :key="item.id">
        <div v-if="item.separator" class="menu-sep" role="separator" />
        <button
          v-else
          type="button"
          class="menu-option"
          role="menuitem"
          :disabled="item.disabled"
          :aria-checked="item.checked"
          @click="runItem(item)"
        >
          <span class="menu-option-main">
            <AppIcon
              v-if="item.icon"
              class="menu-option-icon"
              :name="item.icon"
              :size="14"
              :stroke-width="1.75"
            />
            <span class="menu-option-label">{{ item.label }}</span>
          </span>
          <span v-if="item.checked" class="menu-option-check">
            <AppIcon name="check" :size="13" :stroke-width="2" />
          </span>
          <span v-else-if="item.shortcut" class="menu-option-shortcut">{{ item.shortcut }}</span>
        </button>
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
.app-menu-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--sidebar-bg);
  user-select: none;
}
.app-menu-bar.pos-top,
.app-menu-bar.pos-bottom {
  height: 38px;
  padding: 0 10px;
}
.app-menu-bar.is-titlebar {
  height: var(--desktop-titlebar-height, 38px);
  -webkit-app-region: drag;
}
.app-menu-bar.is-titlebar .menu-trigger,
.app-menu-bar.is-titlebar .menu-actions,
.app-menu-bar.is-titlebar .ghost-icon-btn,
.app-menu-bar.is-titlebar input {
  -webkit-app-region: no-drag;
}
.app-menu-bar.pos-top {
  border-bottom: var(--border-width) solid var(--border);
}
.app-menu-bar.pos-bottom {
  border-top: var(--border-width) solid var(--border);
}
.app-menu-bar.pos-left,
.app-menu-bar.pos-right {
  width: 52px;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  padding: 10px 6px;
}
.app-menu-bar.pos-left {
  border-right: var(--border-width) solid var(--border);
}
.app-menu-bar.pos-right {
  border-left: var(--border-width) solid var(--border);
}
.menu-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.pos-left .menu-brand,
.pos-right .menu-brand {
  justify-content: center;
  padding: 4px 0 8px;
}
.brand-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
  letter-spacing: -0.02em;
  white-space: nowrap;
}
.menu-nav {
  display: flex;
  align-items: center;
  gap: 1px;
  min-width: 0;
}
.pos-left .menu-nav,
.pos-right .menu-nav {
  flex: 1;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  min-height: 0;
  overflow: auto;
}
.menu-item {
  position: relative;
}
.menu-trigger {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 9px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}
.pos-left .menu-trigger,
.pos-right .menu-trigger {
  width: 100%;
  height: 36px;
  justify-content: center;
  padding: 0;
}
.pos-left .menu-trigger-label,
.pos-right .menu-trigger-label {
  display: none;
}
.menu-item.open .menu-trigger,
.menu-trigger:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.menu-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 2px;
}
.pos-left .menu-actions,
.pos-right .menu-actions {
  margin-left: 0;
  margin-top: auto;
  flex-direction: column;
  gap: 4px;
}
</style>

<style>
.menu-dropdown {
  position: fixed;
  z-index: 1200;
  min-width: 240px;
  max-height: min(70vh, 480px);
  overflow: auto;
  padding: 4px;
  border: var(--border-width) solid var(--border);
  border-radius: 8px;
  background: var(--panel-bg);
  box-shadow: 0 10px 28px color-mix(in srgb, #000 18%, transparent);
}
.menu-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  width: 100%;
  min-height: 30px;
  padding: 0 10px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-h);
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
}
.menu-option:hover:not(:disabled) {
  background: var(--primary-soft);
  color: var(--primary);
}
.menu-option:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.menu-option-main {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.menu-option-icon {
  flex-shrink: 0;
  opacity: 0.9;
}
.menu-option-label {
  min-width: 0;
}
.menu-option-shortcut,
.menu-option-check {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 11px;
  font-family: var(--mono);
}
.menu-option-check {
  display: inline-flex;
  color: var(--primary);
}
.menu-sep {
  height: 1px;
  margin: 4px 6px;
  background: var(--border);
}
</style>
