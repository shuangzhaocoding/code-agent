<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import ContextMenu, { type ContextMenuItem } from '@/components/ContextMenu.vue'
import { useAppStore } from '@/stores/app'

type PanelLike = {
  id: string
  api: { close: () => void; setActive?: () => void }
}

type PanelApiLike = {
  id?: string
  close?: () => void
  group?: { panels?: PanelLike[] }
  maximize?: () => void
  isMaximized?: () => boolean
  exitMaximized?: () => void
  setActive?: () => void
}

const { t } = useI18n()
const store = useAppStore()

const props = defineProps<{
  params?: {
    api?: PanelApiLike
    params?: { api?: PanelApiLike }
    title?: string
  }
  api?: PanelApiLike
  containerApi?: unknown
  title?: string
  tabLocation?: string
}>()

const icons: Record<string, string> = {
  workspace: 'home',
  explorer: 'folder',
  search: 'search',
  editor: 'file',
  agent: 'atom',
  terminal: 'terminal',
  ports: 'ports',
  git: 'git',
  skills: 'book',
  plugins: 'puzzle',
  models: 'chip',
  settings: 'sliders',
  trajectory: 'clock',
  memory: 'memory',
}

const menu = ref<{ x: number; y: number } | null>(null)

const panelApi = computed(
  () => props.api || props.params?.api || props.params?.params?.api || null,
)
const id = computed(() => panelApi.value?.id || '')
const info = computed(() => {
  const key = `panels.${id.value}`
  const label = t(key)
  if (icons[id.value] && label !== key) return { icon: icons[id.value], label }
  const title = props.title || props.params?.title
  return { icon: icons[id.value] || 'file', label: title || id.value || t('common.panel') }
})

const dirty = computed(
  () => id.value === 'editor' && store.openFiles.some((f) => f.dirty),
)

const groupPanels = computed(() => panelApi.value?.group?.panels || [])

const menuItems = computed((): ContextMenuItem[] => {
  const panels = groupPanels.value
  const index = panels.findIndex((p) => p.id === id.value)
  const maximized = Boolean(panelApi.value?.isMaximized?.())
  return [
    {
      id: 'maximize',
      label: maximized ? t('panels.tab.restore') : t('panels.tab.maximize'),
      icon: maximized ? 'minimize' : 'maximize',
    },
    { id: 'sep-max', separator: true },
    { id: 'close', label: t('editor.close'), icon: 'close' },
    {
      id: 'close-others',
      label: t('editor.closeOthers'),
      icon: 'close-others',
      disabled: panels.length < 2,
    },
    {
      id: 'close-left',
      label: t('editor.closeLeft'),
      icon: 'close-left',
      disabled: index <= 0,
    },
    {
      id: 'close-right',
      label: t('editor.closeRight'),
      icon: 'close-right',
      disabled: index < 0 || index >= panels.length - 1,
    },
    {
      id: 'close-all',
      label: t('editor.closeAll'),
      icon: 'close-all',
      disabled: panels.length === 0,
    },
  ]
})

function close(e?: Event) {
  e?.preventDefault()
  e?.stopPropagation()
  panelApi.value?.close?.()
}

function onMiddleClick(e: MouseEvent) {
  if (e.button !== 1) return
  e.preventDefault()
  e.stopPropagation()
  close()
}

function onDblClick(e: MouseEvent) {
  if ((e.target as HTMLElement | null)?.closest?.('.ptab-close')) return
  e.preventDefault()
  e.stopPropagation()
  toggleMaximize()
}

function toggleMaximize() {
  const api = panelApi.value
  if (!api?.maximize || !api.exitMaximized || !api.isMaximized) return
  if (api.isMaximized()) api.exitMaximized()
  else api.maximize()
}

function onContextMenu(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  menu.value = { x: e.clientX, y: e.clientY }
}

function onMenuSelect(action: string) {
  const api = panelApi.value
  if (!api) return
  const panels = groupPanels.value
  const index = panels.findIndex((p) => p.id === id.value)
  if (action === 'maximize') {
    toggleMaximize()
    return
  }
  if (action === 'close') {
    api.close?.()
    return
  }
  if (action === 'close-others') {
    for (const p of [...panels]) {
      if (p.id !== id.value) p.api.close()
    }
    return
  }
  if (action === 'close-left' && index > 0) {
    for (const p of panels.slice(0, index)) p.api.close()
    return
  }
  if (action === 'close-right' && index >= 0) {
    for (const p of panels.slice(index + 1)) p.api.close()
    return
  }
  if (action === 'close-all') {
    for (const p of [...panels]) p.api.close()
  }
}

function focusPanelTab(panelId?: string) {
  if (!panelId) return
  requestAnimationFrame(() => {
    const el = document.querySelector(
      `.dv-tab .ptab[data-panel-id="${panelId}"]`,
    ) as HTMLElement | null
    el?.focus()
  })
}

function activateSibling(delta: number) {
  const panels = groupPanels.value
  if (panels.length < 2) return
  const index = panels.findIndex((p) => p.id === id.value)
  if (index < 0) return
  const next = panels[(index + delta + panels.length) % panels.length]
  next?.api.setActive?.()
  focusPanelTab(next?.id)
}

function onTabKeydown(e: KeyboardEvent) {
  const panels = groupPanels.value
  const index = panels.findIndex((p) => p.id === id.value)

  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    if (panels.length < 2 || index < 0) return
    e.preventDefault()
    e.stopPropagation()
    activateSibling(e.key === 'ArrowRight' ? 1 : -1)
    return
  }

  if (e.key === 'Home' || e.key === 'End') {
    if (panels.length < 2 || index < 0) return
    e.preventDefault()
    e.stopPropagation()
    const target = e.key === 'Home' ? panels[0] : panels[panels.length - 1]
    target?.api.setActive?.()
    focusPanelTab(target?.id)
    return
  }

  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    e.stopPropagation()
    panelApi.value?.setActive?.()
    return
  }

  if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault()
    e.stopPropagation()
    close()
  }
}
</script>

<template>
  <div
    class="ptab"
    :class="{ dirty }"
    :title="dirty ? `${info.label} (${t('panels.tab.dirty')})` : info.label"
    :data-panel-id="id"
    tabindex="0"
    @contextmenu="onContextMenu"
    @dblclick="onDblClick"
    @mousedown.middle="onMiddleClick"
    @auxclick.middle.prevent="close"
    @keydown="onTabKeydown"
  >
    <AppIcon class="ptab-ico" :name="info.icon" :size="16" :stroke-width="1.75" />
    <span class="lbl">{{ info.label }}</span>
    <span v-if="dirty" class="ptab-dirty" aria-hidden="true" />
    <button
      type="button"
      class="ghost-icon-btn ptab-close"
      :title="t('common.close')"
      @mousedown.stop.prevent
      @click="close"
    >
      <AppIcon name="close" :size="12" :stroke-width="1.75" />
    </button>
  </div>

  <Teleport to="body">
    <ContextMenu
      v-if="menu"
      :x="menu.x"
      :y="menu.y"
      :items="menuItems"
      @select="onMenuSelect"
      @close="menu = null"
    />
  </Teleport>
</template>

<style scoped>
.ptab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 100%;
  padding: 0 6px 0 8px;
  color: inherit;
  outline: none;
}
.ptab:focus-visible {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 55%, transparent);
}
.ptab-ico {
  opacity: 0.82;
}
.lbl {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.01em;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: inherit;
}
.ptab-dirty {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
  margin-right: 1px;
}
.ptab-close {
  margin-left: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.ptab:hover .ptab-close,
.ptab:focus-within .ptab-close {
  opacity: var(--ghost-hover-opacity);
}
.ptab-close:hover {
  opacity: 1 !important;
}
@media (hover: none) {
  .ptab-close {
    opacity: var(--ghost-hover-opacity);
  }
}
</style>
