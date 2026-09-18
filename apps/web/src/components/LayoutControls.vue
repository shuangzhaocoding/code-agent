<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon, { type AppIconName } from '@/components/AppIcon.vue'
import { useToast } from '@/composables/useToast'
import { useAppStore } from '@/stores/app'
import {
  getStoredLayoutSelection,
  LAYOUT_PRESET_IDS,
  listSavedLayouts,
  type LayoutPresetId,
  type LayoutViewState,
  type SavedLayout,
} from '@/utils/layoutPresets'
import {
  getMenuBarPosition,
  isMenuBarPosition,
  MENU_BAR_POSITIONS,
  setMenuBarPosition,
  type MenuBarPosition,
} from '@/utils/layoutPrefs'

const { t } = useI18n()
const toast = useToast()
const store = useAppStore()
const importInput = ref<HTMLInputElement | null>(null)
const activeId = ref(getStoredLayoutSelection(store.workspaceId))
const layoutDirty = ref(false)
const savedLayouts = ref<SavedLayout[]>(listSavedLayouts(store.workspaceId))
const menuPosition = ref<MenuBarPosition>(getMenuBarPosition())

const PRESET_ICONS: Record<LayoutPresetId, string> = {
  chat: 'chat',
  code: 'file',
}

const POSITION_ICONS: Record<MenuBarPosition, AppIconName> = {
  top: 'menu',
  left: 'layout-left',
  right: 'layout-right',
  bottom: 'layout-bottom',
}

function syncActivePreset(id?: string) {
  activeId.value = id || getStoredLayoutSelection(store.workspaceId)
  savedLayouts.value = listSavedLayouts(store.workspaceId)
}

function onPresetChanged(e: Event) {
  const id = (e as CustomEvent<{ id?: string }>).detail?.id
  syncActivePreset(id)
}

function onLayoutState(e: Event) {
  const detail = (e as CustomEvent<LayoutViewState>).detail
  if (!detail) return
  activeId.value = detail.id
  layoutDirty.value = Boolean(detail.dirty)
  savedLayouts.value = detail.saved ?? listSavedLayouts(store.workspaceId)
}

function onNamedChanged(e: Event) {
  const next = (e as CustomEvent<{ saved?: SavedLayout[] }>).detail?.saved
  savedLayouts.value = next ?? listSavedLayouts(store.workspaceId)
}

function onMenuPositionChanged(e: Event) {
  const position = (e as CustomEvent<{ position: MenuBarPosition }>).detail?.position
  if (isMenuBarPosition(position)) menuPosition.value = position
}

function onMenuPositionSelect(value: MenuBarPosition) {
  menuPosition.value = value
  setMenuBarPosition(value)
}

function resetLayout() {
  window.dispatchEvent(new Event('ca-layout-reset'))
}

function applyPreset(id: LayoutPresetId) {
  window.dispatchEvent(new CustomEvent('ca-layout-preset', { detail: { id } }))
}

function onPresetApplied(e: Event) {
  const id = (e as CustomEvent<{ id?: string; reset?: boolean }>).detail?.id
  if (id) syncActivePreset(id)
}

function saveCurrentLayout() {
  window.dispatchEvent(new Event('ca-layout-save'))
}

function applySaved(id: string) {
  window.dispatchEvent(new CustomEvent('ca-layout-preset', { detail: { id } }))
}

function deleteSaved(id: string) {
  window.dispatchEvent(new CustomEvent('ca-layout-named-delete', { detail: { id } }))
}

function exportLayout() {
  window.dispatchEvent(new Event('ca-layout-export'))
}

function pickImport() {
  importInput.value?.click()
}

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

onMounted(() => {
  syncActivePreset()
  menuPosition.value = getMenuBarPosition()
  window.addEventListener('ca-layout-preset-changed', onPresetChanged as EventListener)
  window.addEventListener('ca-layout-preset-applied', onPresetApplied as EventListener)
  window.addEventListener('ca-layout-state', onLayoutState as EventListener)
  window.addEventListener('ca-layout-named-changed', onNamedChanged as EventListener)
  window.addEventListener('ca-menu-position', onMenuPositionChanged as EventListener)
})
onUnmounted(() => {
  window.removeEventListener('ca-layout-preset-changed', onPresetChanged as EventListener)
  window.removeEventListener('ca-layout-preset-applied', onPresetApplied as EventListener)
  window.removeEventListener('ca-layout-state', onLayoutState as EventListener)
  window.removeEventListener('ca-layout-named-changed', onNamedChanged as EventListener)
  window.removeEventListener('ca-menu-position', onMenuPositionChanged as EventListener)
})

watch(
  () => store.workspaceId,
  () => syncActivePreset(),
)
</script>

<template>
  <section class="layout-controls">
    <div class="menu-position-block">
      <h3>{{ t('menu.positionLabel') }}</h3>
      <p class="layout-lead">{{ t('menu.positionLead') }}</p>
      <div class="position-grid" role="radiogroup" :aria-label="t('menu.positionLabel')">
        <button
          v-for="pos in MENU_BAR_POSITIONS"
          :key="pos"
          type="button"
          class="position-card"
          role="radio"
          :aria-checked="menuPosition === pos"
          :class="{ active: menuPosition === pos }"
          @click="onMenuPositionSelect(pos)"
        >
          <span class="position-icon">
            <AppIcon :name="POSITION_ICONS[pos]" :size="16" />
          </span>
          <strong>{{ t(`menu.positionsShort.${pos}`) }}</strong>
        </button>
      </div>
    </div>

    <h3>{{ t('layout.title') }}</h3>
    <p class="layout-lead">{{ t('layout.lead') }}</p>
    <p v-if="layoutDirty" class="layout-current">{{ t('layout.current') }} · {{ t('layout.currentHint') }}</p>
    <div class="layout-actions">
      <button type="button" class="btn" @click="saveCurrentLayout">
        <AppIcon name="save" :size="14" />
        {{ t('layout.save') }}
      </button>
      <button type="button" class="btn" @click="resetLayout">
        <AppIcon name="refresh" :size="14" />
        {{ t('layout.reset') }}
      </button>
      <button type="button" class="btn" @click="exportLayout">
        <AppIcon name="download" :size="14" />
        {{ t('layout.export') }}
      </button>
      <button type="button" class="btn" @click="pickImport">
        <AppIcon name="upload" :size="14" />
        {{ t('layout.import') }}
      </button>
      <input ref="importInput" type="file" accept="application/json,.json" hidden @change="onImportFile" />
    </div>
    <div class="preset-grid">
      <button
        v-for="id in LAYOUT_PRESET_IDS"
        :key="id"
        type="button"
        class="preset-card"
        :class="{ active: !layoutDirty && activeId === id }"
        @click="applyPreset(id)"
      >
        <span class="preset-icon">
          <AppIcon :name="PRESET_ICONS[id]" :size="16" />
        </span>
        <span class="preset-copy">
          <strong>{{ t(`layout.presets.${id}`) }}</strong>
          <span>{{ t(`layout.presetsDesc.${id}`) }}</span>
        </span>
      </button>
    </div>

    <h3>{{ t('layout.namedGroup') }}</h3>
    <p class="layout-lead">{{ t('layout.savedLead') }}</p>
    <p v-if="!savedLayouts.length" class="layout-empty">{{ t('layout.savedEmpty') }}</p>
    <div v-else class="saved-list">
      <div
        v-for="item in savedLayouts"
        :key="item.id"
        class="saved-row"
        :class="{ active: !layoutDirty && activeId === item.id }"
      >
        <button type="button" class="saved-main" @click="applySaved(item.id)">
          <span class="preset-icon">
            <AppIcon name="pin" :size="16" />
          </span>
          <span class="preset-copy">
            <strong>{{ item.name }}</strong>
            <span>{{ t('layout.savedHint') }}</span>
          </span>
        </button>
        <button
          type="button"
          class="saved-delete"
          :title="t('common.delete')"
          :aria-label="t('layout.deleteNamed', { name: item.name })"
          @click="deleteSaved(item.id)"
        >
          <AppIcon name="trash" :size="14" />
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.layout-controls {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 0;
}
.menu-position-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: var(--border-width) solid var(--border);
  margin-bottom: 4px;
}
.position-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  max-width: 320px;
}
.position-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  text-align: left;
  cursor: pointer;
  color: var(--text-h);
}
.position-card:hover {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 6%, var(--panel-bg));
}
.position-card.active {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 10%, var(--panel-bg));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 35%, transparent);
}
.position-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: var(--primary-soft);
  color: var(--primary);
  flex-shrink: 0;
}
.position-card strong {
  font-size: 12px;
  font-weight: 600;
}
.layout-controls h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
}
.layout-lead {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.45;
}
.layout-current {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
  line-height: 1.45;
}
.layout-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.layout-actions .btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.preset-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.preset-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  text-align: left;
  cursor: pointer;
}
.preset-card:hover {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 6%, var(--panel-bg));
}
.preset-card.active {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 10%, var(--panel-bg));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 35%, transparent);
}
.preset-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: var(--primary-soft);
  color: var(--primary);
  flex-shrink: 0;
}
.preset-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.preset-copy strong {
  font-size: 12px;
  color: var(--text-h);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.preset-dirty {
  font-size: 10px;
  font-weight: 600;
  color: var(--primary);
}
.preset-copy span {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.35;
}
.layout-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}
.saved-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.saved-row {
  display: flex;
  align-items: stretch;
  gap: 4px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
}
.saved-row:hover {
  border-color: var(--primary);
}
.saved-row.active {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 10%, var(--panel-bg));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 35%, transparent);
}
.saved-main {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
  min-width: 0;
  padding: 12px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  color: inherit;
}
.saved-delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
}
.saved-delete:hover {
  background: color-mix(in srgb, var(--danger, #d14343) 12%, transparent);
  color: var(--danger, #d14343);
}
@media (max-width: 560px) {
  .preset-grid,
  .position-grid {
    grid-template-columns: 1fr;
  }
}
</style>
