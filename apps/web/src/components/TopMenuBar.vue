<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon, { type AppIconName } from '@/components/AppIcon.vue'
import BrandMark from '@/components/BrandMark.vue'
import ShortcutsHelp from '@/components/ShortcutsHelp.vue'
import { useToast } from '@/composables/useToast'
import { useAppStore } from '@/stores/app'
import {
  MENU_BAR_POSITIONS,
  setMenuBarPosition,
  type MenuBarPosition,
} from '@/utils/layoutPrefs'
import { isMacMod, paletteShortcutLabel } from '@/utils/relativeTime'
import { isDesktopApp, openDesktopWindow } from '@/utils/desktop'

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
  /** Hide command/theme actions when DesktopTitleBar already shows them. */
  hideActions?: boolean
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
const activeOption = ref(-1)
const shortcutsOpen = ref(false)
const rootEl = ref<HTMLElement | null>(null)
const dropdownEl = ref<HTMLElement | null>(null)
const importInput = ref<HTMLInputElement | null>(null)
const dropdownStyle = ref<Record<string, string>>({})
const MENU_ORDER: MenuId[] = ['file', 'edit', 'panel', 'help']

const modKey = isMacMod() ? '⌘' : 'Ctrl+'
const commandShortcut = paletteShortcutLabel()
const fileShortcut = isMacMod() ? '⌘P' : 'Ctrl+P'
const searchShortcut = isMacMod() ? '⌘⇧F' : 'Ctrl+Shift+F'
const saveShortcut = `${modKey}S`
const newChatShortcut = `${modKey}N`
const newWindowShortcut = isMacMod() ? '⌘⇧N' : 'Ctrl+Shift+N'
const isDesktop = isDesktopApp()

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
  preview: 'globe',
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
  activeOption.value = -1
}

async function openMenuById(id: MenuId) {
  openMenu.value = id
  activeOption.value = 0
  await nextTick()
  const trigger = rootEl.value?.querySelector(
    `.menu-item.open .menu-trigger`,
  ) as HTMLElement | null
  if (trigger) {
    placeDropdown(trigger)
    requestAnimationFrame(() => placeDropdown(trigger))
  }
}

function moveActiveOption(delta: number) {
  const items = activeMenuItems.value
  if (!items.length) {
    activeOption.value = -1
    return
  }
  const next = activeOption.value < 0 ? (delta > 0 ? 0 : items.length - 1) : activeOption.value + delta
  activeOption.value = ((next % items.length) + items.length) % items.length
  void nextTick(() => {
    dropdownEl.value
      ?.querySelector('.menu-option.active')
      ?.scrollIntoView({ block: 'nearest' })
  })
}

function switchMenu(delta: number) {
  if (!openMenu.value) return
  const idx = MENU_ORDER.indexOf(openMenu.value)
  if (idx < 0) return
  const next = MENU_ORDER[(idx + delta + MENU_ORDER.length) % MENU_ORDER.length]
  void openMenuById(next)
}

function placeDropdown(trigger: HTMLElement) {
  const rect = trigger.getBoundingClientRect()
  const gap = 6
  const margin = 8
  const el = dropdownEl.value
  const width = Math.max(el?.offsetWidth || 240, 240)
  const height = Math.max(el?.offsetHeight || 48, 48)
  const vw = window.innerWidth
  const vh = window.innerHeight

  let top: number | null = null
  let left: number | null = null
  let right: number | null = null
  let bottom: number | null = null

  if (props.position === 'top') {
    top = rect.bottom + gap
    left = rect.left
    if (top + height > vh - margin) {
      top = Math.max(margin, rect.top - height - gap)
    }
  } else if (props.position === 'bottom') {
    bottom = vh - rect.top + gap
    left = rect.left
    const estimatedTop = vh - bottom - height
    if (estimatedTop < margin) {
      bottom = null
      top = Math.min(rect.bottom + gap, vh - height - margin)
    }
  } else if (props.position === 'left') {
    top = rect.top
    left = rect.right + gap
    if (left + width > vw - margin) {
      left = Math.max(margin, rect.left - width - gap)
    }
  } else {
    top = rect.top
    right = vw - rect.left + gap
    const estimatedLeft = vw - right - width
    if (estimatedLeft < margin) {
      right = null
      left = Math.min(rect.right + gap, vw - width - margin)
    }
  }

  if (left != null) {
    left = Math.min(Math.max(margin, left), Math.max(margin, vw - width - margin))
  }
  if (top != null) {
    top = Math.min(Math.max(margin, top), Math.max(margin, vh - height - margin))
  }

  const style: Record<string, string> = {}
  if (top != null) style.top = `${Math.round(top)}px`
  if (left != null) style.left = `${Math.round(left)}px`
  if (right != null) style.right = `${Math.round(right)}px`
  if (bottom != null) style.bottom = `${Math.round(bottom)}px`
  dropdownStyle.value = style
}

async function toggleMenu(id: MenuId, e: MouseEvent) {
  if (openMenu.value === id) {
    closeMenu()
    return
  }
  openMenu.value = id
  activeOption.value = 0
  const trigger = e.currentTarget as HTMLElement
  await nextTick()
  placeDropdown(trigger)
  requestAnimationFrame(() => placeDropdown(trigger))
}

function onMenuEnter(id: MenuId, e: MouseEvent) {
  if (!openMenu.value || openMenu.value === id) return
  openMenu.value = id
  activeOption.value = 0
  const trigger = e.currentTarget as HTMLElement
  void nextTick(() => placeDropdown(trigger))
}

watch(openMenu, (id) => {
  if (!id) activeOption.value = -1
})

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
    ...(isDesktop
      ? [
          {
            id: 'new-window',
            label: t('menu.items.newWindow'),
            icon: 'layout-right' as const,
            shortcut: newWindowShortcut,
            run: async () => {
              const ok = await openDesktopWindow()
              if (!ok) toast.error(t('menu.items.newWindowFailed'))
            },
          } satisfies MenuItem,
        ]
      : []),
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
        window.dispatchEvent(new CustomEvent('ca-editor-save', { detail: { notify: true } }))
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
    ['explorer', 'search', 'editor', 'preview', 'terminal'],
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
      run: () => {
        shortcutsOpen.value = true
      },
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
const activeMenuItems = computed(() =>
  (activeMenu.value?.items || []).filter((item) => !item.separator && !item.disabled),
)
const activeItemId = computed(() => activeMenuItems.value[activeOption.value]?.id || null)

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
  if (!openMenu.value) return
  const sideRail = props.position === 'left' || props.position === 'right'
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    closeMenu()
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    e.stopPropagation()
    moveActiveOption(1)
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    e.stopPropagation()
    moveActiveOption(-1)
    return
  }
  if (e.key === 'ArrowRight') {
    e.preventDefault()
    e.stopPropagation()
    switchMenu(sideRail ? 1 : 1)
    return
  }
  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    e.stopPropagation()
    switchMenu(sideRail ? -1 : -1)
    return
  }
  if (e.key === 'Enter' || e.key === ' ') {
    const item = activeMenuItems.value[activeOption.value]
    if (!item) return
    e.preventDefault()
    e.stopPropagation()
    void runItem(item)
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

    <div v-if="!hideActions" class="menu-actions">
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
          :class="{ active: activeItemId === item.id }"
          role="menuitem"
          :disabled="item.disabled"
          :aria-checked="item.checked"
          @mouseenter="
            activeOption = activeMenuItems.findIndex((it) => it.id === item.id)
          "
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

  <ShortcutsHelp v-model:open="shortcutsOpen" />
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
.app-menu-bar.pos-left:not(:has(.menu-actions)),
.app-menu-bar.pos-right:not(:has(.menu-actions)) {
  padding-bottom: 6px;
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
.menu-option:hover:not(:disabled),
.menu-option.active:not(:disabled) {
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
