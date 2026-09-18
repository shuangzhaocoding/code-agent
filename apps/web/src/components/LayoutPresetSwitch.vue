<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import { useAppStore } from '@/stores/app'
import {
  getStoredLayoutSelection,
  isLayoutPresetId,
  LAYOUT_PRESET_IDS,
  listSavedLayouts,
  type LayoutPresetId,
  type LayoutViewState,
  type SavedLayout,
} from '@/utils/layoutPresets'

defineProps<{
  compact?: boolean
  vertical?: boolean
}>()

const { t } = useI18n()
const store = useAppStore()
const active = ref(getStoredLayoutSelection(store.workspaceId))
const dirty = ref(false)
const saved = ref<SavedLayout[]>(listSavedLayouts(store.workspaceId))
const open = ref(false)
const ready = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const menuStyle = ref<Record<string, string>>({})

const activeSaved = computed(() => saved.value.find((item) => item.id === active.value) || null)

const selectedId = computed(() => (dirty.value ? 'current' : active.value))
const selectedLabel = computed(() => {
  if (dirty.value) return t('layout.current')
  if (isLayoutPresetId(active.value)) return t(`layout.presets.${active.value}`)
  return activeSaved.value?.name || t('layout.current')
})
const selectedIcon = computed(() => {
  if (dirty.value) return 'sliders'
  if (active.value === 'code') return 'file'
  if (active.value === 'chat') return 'chat'
  return 'pin'
})
const selectedHint = computed(() => {
  if (dirty.value) return t('layout.currentHint')
  if (isLayoutPresetId(active.value)) return t(`layout.presetsDesc.${active.value}`)
  return t('layout.savedHint')
})

type LayoutOption =
  | { id: 'current'; icon: string }
  | { id: LayoutPresetId; icon: string }

const presetOptions = computed<LayoutOption[]>(() => {
  const presets: LayoutOption[] = LAYOUT_PRESET_IDS.map((id) => ({
    id,
    icon: id === 'code' ? 'file' : 'chat',
  }))
  if (!dirty.value) return presets
  return [{ id: 'current', icon: 'sliders' }, ...presets]
})

function optionLabel(id: LayoutOption['id']) {
  return id === 'current' ? t('layout.current') : t(`layout.presets.${id}`)
}

function optionDesc(id: LayoutOption['id']) {
  return id === 'current' ? t('layout.currentHint') : t(`layout.presetsDesc.${id}`)
}

function sync(state?: LayoutViewState) {
  saved.value = state?.saved ?? listSavedLayouts(store.workspaceId)
  if (state) {
    active.value = state.id
    dirty.value = Boolean(state.dirty)
    return
  }
  active.value = getStoredLayoutSelection(store.workspaceId)
}

function onState(e: Event) {
  sync((e as CustomEvent<LayoutViewState>).detail)
}

function onPresetChanged(e: Event) {
  const id = (e as CustomEvent<{ id?: string }>).detail?.id
  if (typeof id === 'string' && id) active.value = id
}

function onNamedChanged(e: Event) {
  const next = (e as CustomEvent<{ saved?: SavedLayout[] }>).detail?.saved
  saved.value = next ?? listSavedLayouts(store.workspaceId)
}

function updateMenuPosition() {
  const el = trigger.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const width = Math.max(rect.width, 248)
  const gap = 4
  let left = rect.left
  left = Math.max(8, Math.min(left, window.innerWidth - width - 8))
  const spaceBelow = window.innerHeight - rect.bottom - 8
  const openUp = spaceBelow < 180 && rect.top > spaceBelow
  menuStyle.value = {
    position: 'fixed',
    left: `${left}px`,
    width: `${width}px`,
    zIndex: '12000',
    ...(openUp
      ? { top: 'auto', bottom: `${window.innerHeight - rect.top + gap}px` }
      : { top: `${rect.bottom + gap}px`, bottom: 'auto' }),
  }
}

async function openMenu() {
  saved.value = listSavedLayouts(store.workspaceId)
  updateMenuPosition()
  ready.value = false
  open.value = true
  await nextTick()
  requestAnimationFrame(() => {
    updateMenuPosition()
    ready.value = true
  })
}

function closeMenu() {
  open.value = false
  ready.value = false
}

function toggleMenu() {
  if (open.value) closeMenu()
  else void openMenu()
}

function pick(id: string) {
  closeMenu()
  if (id === 'current') return
  if (id === active.value && !dirty.value) return
  window.dispatchEvent(new CustomEvent('ca-layout-preset', { detail: { id } }))
}

function saveCurrent() {
  closeMenu()
  window.dispatchEvent(new Event('ca-layout-save'))
}

function removeSaved(id: string) {
  closeMenu()
  window.dispatchEvent(new CustomEvent('ca-layout-named-delete', { detail: { id } }))
}

function onDocPointer(e: PointerEvent) {
  const target = e.target as Node
  if (root.value?.contains(target) || menuRef.value?.contains(target)) return
  closeMenu()
}

function onKey(e: KeyboardEvent) {
  if (!open.value) return
  if (e.key === 'Escape') {
    e.preventDefault()
    closeMenu()
    trigger.value?.focus()
  }
}

onMounted(() => {
  sync()
  window.addEventListener('ca-layout-state', onState as EventListener)
  window.addEventListener('ca-layout-preset-changed', onPresetChanged as EventListener)
  window.addEventListener('ca-layout-named-changed', onNamedChanged as EventListener)
  document.addEventListener('pointerdown', onDocPointer)
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('ca-layout-state', onState as EventListener)
  window.removeEventListener('ca-layout-preset-changed', onPresetChanged as EventListener)
  window.removeEventListener('ca-layout-named-changed', onNamedChanged as EventListener)
  document.removeEventListener('pointerdown', onDocPointer)
  window.removeEventListener('keydown', onKey)
})

watch(
  () => store.workspaceId,
  () => sync(),
)
</script>

<template>
  <div ref="root" class="layout-switch" :class="{ compact, vertical, open, dirty }">
    <button
      ref="trigger"
      type="button"
      class="layout-switch-trigger"
      :aria-expanded="open"
      aria-haspopup="listbox"
      :aria-label="t('layout.title')"
      :title="selectedHint"
      @click="toggleMenu"
    >
      <AppIcon :name="selectedIcon" :size="13" />
      <span class="layout-switch-label">{{ selectedLabel }}</span>
      <AppIcon class="layout-switch-chev" name="chevron" :size="14" :stroke-width="1.75" />
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        class="layout-switch-menu"
        :class="{ ready }"
        :style="menuStyle"
        role="listbox"
        :aria-label="t('layout.title')"
        @pointerdown.stop
      >
        <button
          v-for="option in presetOptions"
          :key="option.id"
          type="button"
          class="layout-switch-option"
          :class="{ active: option.id === selectedId }"
          role="option"
          :aria-selected="option.id === selectedId"
          @click="pick(option.id)"
        >
          <AppIcon :name="option.icon" :size="14" />
          <span class="layout-switch-option-copy">
            <span class="layout-switch-option-label">{{ optionLabel(option.id) }}</span>
            <span class="layout-switch-option-desc">{{ optionDesc(option.id) }}</span>
          </span>
        </button>

        <template v-if="saved.length">
          <div class="layout-switch-sep" role="separator" />
          <div class="layout-switch-group">{{ t('layout.namedGroup') }}</div>
          <div v-for="item in saved" :key="item.id" class="layout-switch-saved">
            <button
              type="button"
              class="layout-switch-option"
              :class="{ active: item.id === selectedId }"
              role="option"
              :aria-selected="item.id === selectedId"
              @click="pick(item.id)"
            >
              <AppIcon name="pin" :size="14" />
              <span class="layout-switch-option-copy">
                <span class="layout-switch-option-label">{{ item.name }}</span>
                <span class="layout-switch-option-desc">{{ t('layout.savedHint') }}</span>
              </span>
            </button>
            <button
              type="button"
              class="layout-switch-delete"
              :title="t('common.delete')"
              :aria-label="t('layout.deleteNamed', { name: item.name })"
              @click.stop="removeSaved(item.id)"
            >
              <AppIcon name="trash" :size="13" />
            </button>
          </div>
        </template>

        <div class="layout-switch-sep" role="separator" />
        <button type="button" class="layout-switch-save" @click="saveCurrent">
          <AppIcon name="save" :size="14" />
          <span>{{ t('layout.save') }}</span>
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.layout-switch {
  position: relative;
  flex-shrink: 0;
  min-width: 0;
}
.layout-switch.vertical {
  width: 100%;
}
.layout-switch-trigger {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 6px 0 8px;
  border: var(--border-width) solid var(--border);
  border-radius: 8px;
  background: var(--code-bg);
  color: var(--text-h);
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.vertical .layout-switch-trigger {
  width: 100%;
  height: 28px;
  justify-content: center;
}
.layout-switch-trigger:hover,
.layout-switch.open .layout-switch-trigger {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
}
.layout-switch.dirty .layout-switch-trigger {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 40%, transparent);
}
.layout-switch-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 140px;
}
.compact .layout-switch-label {
  display: none;
}
.vertical .layout-switch-label {
  display: none;
}
.layout-switch-chev {
  opacity: 0.7;
  flex-shrink: 0;
}
.layout-switch-menu {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px;
  border: var(--border-width) solid var(--border);
  border-radius: 10px;
  background: var(--panel-bg);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.14);
  opacity: 0;
  pointer-events: none;
  max-height: min(70vh, 420px);
  overflow: auto;
}
.layout-switch-menu.ready {
  opacity: 1;
  pointer-events: auto;
}
html[data-theme='dark'] .layout-switch-menu {
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.45);
}
.layout-switch-option {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-h);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.layout-switch-option:hover,
.layout-switch-option.active {
  background: color-mix(in srgb, var(--text-h) 6%, transparent);
}
.layout-switch-option-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.layout-switch-option-label {
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.layout-switch-option-desc {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  line-height: 1.35;
}
.layout-switch-sep {
  height: 1px;
  margin: 4px 6px;
  background: var(--border);
}
.layout-switch-group {
  padding: 4px 8px 2px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.layout-switch-saved {
  display: flex;
  align-items: stretch;
  gap: 2px;
}
.layout-switch-saved .layout-switch-option {
  flex: 1;
  min-width: 0;
}
.layout-switch-delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  flex-shrink: 0;
  margin: 2px 2px 2px 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.layout-switch-delete:hover {
  background: color-mix(in srgb, var(--danger, #d14343) 12%, transparent);
  color: var(--danger, #d14343);
}
.layout-switch-save {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-h);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}
.layout-switch-save:hover {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  color: var(--primary);
}
</style>
