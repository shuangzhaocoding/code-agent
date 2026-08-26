<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import type { AppIconName } from '@/components/AppIcon.vue'

export type ToolbarSelectOption = {
  value: string | null
  label: string
  description?: string
  icon?: AppIconName | string
  accent?: string
  group?: string
  badge?: string
  badgeKind?: 'ok' | 'fail' | 'unknown'
  children?: ToolbarSelectOption[]
}

const { t } = useI18n()
const props = withDefaults(
  defineProps<{
    modelValue: string | null
    options: ToolbarSelectOption[]
    placeholder?: string
    displayLabel?: string
    selectedChildValue?: string | null
    minWidth?: number
    grow?: boolean
    searchable?: boolean
    searchPlaceholder?: string
  }>(),
  {
    placeholder: '',
    displayLabel: '',
    selectedChildValue: null,
    minWidth: 96,
    grow: false,
    searchable: false,
    searchPlaceholder: '',
  },
)

const placeholderText = computed(() => props.placeholder || t('common.select'))
const searchText = computed(() => props.searchPlaceholder || t('common.search'))

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
  select: [payload: { option: ToolbarSelectOption; child?: ToolbarSelectOption }]
}>()

const open = ref(false)
const menuReady = ref(false)
const expandedValue = ref<string | null>(null)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const submenuRef = ref<HTMLElement | null>(null)
const menuStyle = ref<Record<string, string>>({})
const submenuStyle = ref<Record<string, string>>({})
const expandAnchor = ref<HTMLElement | null>(null)
const query = ref('')
const searchInput = ref<HTMLInputElement | null>(null)

const selected = computed(() => props.options.find((o) => o.value === props.modelValue))
const expandedOption = computed(() => props.options.find((o) => String(o.value) === expandedValue.value && o.children?.length) || null)

const visibleOptions = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.options
  return props.options.filter((option) => {
    const hay = `${option.label} ${option.description || ''} ${option.value || ''}`.toLowerCase()
    return hay.includes(q)
  })
})

const groupedOptions = computed(() => {
  const items = visibleOptions.value
  const hasGroup = items.some((o) => o.group)
  if (!hasGroup) return [{ group: '', items }]
  const map = new Map<string, ToolbarSelectOption[]>()
  for (const option of items) {
    const key = option.group || ''
    const list = map.get(key) || []
    list.push(option)
    map.set(key, list)
  }
  return [...map.entries()].map(([group, items]) => ({ group, items }))
})

function updateMenuPosition() {
  const el = trigger.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const menuWidth = Math.min(Math.max(rect.width, 220), 320)
  let left = rect.left
  if (left + menuWidth > window.innerWidth - 8) left = window.innerWidth - menuWidth - 8
  left = Math.max(8, left)

  menuStyle.value = {
    position: 'fixed',
    left: `${left}px`,
    top: `${Math.max(8, rect.top)}px`,
    transform: 'translateY(calc(-100% - 8px))',
    width: `${menuWidth}px`,
    zIndex: '1000',
  }
}

let layoutCleanup: (() => void) | null = null
let positionRaf = 0

function updateSubmenuPosition(anchor?: HTMLElement | null) {
  const item = anchor || expandAnchor.value
  const menu = menuRef.value
  if (!item || !expandedOption.value) return
  const itemRect = item.getBoundingClientRect()
  const menuRect = menu?.getBoundingClientRect()
  const width = 200
  const gap = 6
  let left = (menuRect?.right ?? itemRect.right) + gap
  if (left + width > window.innerWidth - 8) {
    left = (menuRect?.left ?? itemRect.left) - width - gap
  }
  left = Math.max(8, left)
  const maxHeight = Math.min(280, window.innerHeight - 16)
  let top = itemRect.top
  if (top + 120 > window.innerHeight - 8) top = window.innerHeight - Math.min(maxHeight, 180) - 8
  top = Math.max(8, top)
  submenuStyle.value = {
    position: 'fixed',
    left: `${left}px`,
    top: `${top}px`,
    width: `${width}px`,
    maxHeight: `${maxHeight}px`,
    zIndex: '1001',
  }
}

function schedulePositionUpdate() {
  if (positionRaf) return
  positionRaf = requestAnimationFrame(() => {
    positionRaf = 0
    if (open.value) {
      updateMenuPosition()
      updateSubmenuPosition()
    }
  })
}

function bindLayoutListeners() {
  layoutCleanup?.()
  const onResize = () => schedulePositionUpdate()
  const onScroll = () => schedulePositionUpdate()
  window.addEventListener('resize', onResize)
  window.addEventListener('scroll', onScroll, true)
  layoutCleanup = () => {
    window.removeEventListener('resize', onResize)
    window.removeEventListener('scroll', onScroll, true)
    layoutCleanup = null
  }
}

function scrollToSelected() {
  const list = menuRef.value?.querySelector<HTMLElement>('.menu-body') || menuRef.value
  if (!list) return
  const active = list.querySelector<HTMLElement>('.menu-item.active')
  if (!active) return
  const listRect = list.getBoundingClientRect()
  const itemRect = active.getBoundingClientRect()
  const delta = itemRect.top + itemRect.height / 2 - (listRect.top + listRect.height / 2)
  list.scrollTop += delta
}

function openMenu() {
  query.value = ''
  updateMenuPosition()
  menuReady.value = false
  open.value = true
  void nextTick(() => {
    updateMenuPosition()
    requestAnimationFrame(() => {
      scrollToSelected()
      menuReady.value = true
      bindLayoutListeners()
      searchInput.value?.focus()
    })
  })
}

function closeMenu() {
  open.value = false
  menuReady.value = false
  expandedValue.value = null
  expandAnchor.value = null
  query.value = ''
  layoutCleanup?.()
}

function toggleMenu() {
  if (open.value) closeMenu()
  else openMenu()
}

function pickFirstMatch() {
  const first = visibleOptions.value[0]
  if (first) pick(first)
}

function pick(option: ToolbarSelectOption, child?: ToolbarSelectOption) {
  emit('update:modelValue', option.value)
  emit('select', { option, child })
  closeMenu()
}

function expandOption(option: ToolbarSelectOption, anchor: EventTarget | null) {
  if (!option.children?.length) {
    expandedValue.value = null
    expandAnchor.value = null
    return
  }
  expandedValue.value = String(option.value)
  expandAnchor.value = (anchor as HTMLElement) || null
  void nextTick(() => updateSubmenuPosition(expandAnchor.value))
}

function onItemClick(option: ToolbarSelectOption, event: MouseEvent) {
  if (option.children?.length) {
    expandOption(option, event.currentTarget)
    return
  }
  pick(option)
}

function onDocPointer(e: PointerEvent) {
  const target = e.target as Node
  if (root.value?.contains(target) || menuRef.value?.contains(target) || submenuRef.value?.contains(target)) return
  closeMenu()
}

onMounted(() => document.addEventListener('pointerdown', onDocPointer))
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointer)
  layoutCleanup?.()
  if (positionRaf) cancelAnimationFrame(positionRaf)
})
</script>

<template>
  <div
    ref="root"
    class="toolbar-select"
    :class="{ open, grow }"
    :style="{ '--select-min-w': `${minWidth}px` }"
  >
    <button
      ref="trigger"
      type="button"
      class="toolbar-select-trigger"
      :class="{ placeholder: !selected }"
      :aria-expanded="open"
      @pointerdown.stop
      @click.stop="toggleMenu"
    >
      <span
        v-if="selected?.icon"
        class="trigger-icon"
        :style="selected.accent ? { '--accent': selected.accent } : undefined"
      >
        <AppIcon :name="selected.icon" :size="14" />
      </span>
      <span class="trigger-copy">
        <span class="trigger-label">
          {{ displayLabel || selected?.label || placeholderText }}
          <em v-if="selected?.badge" class="option-badge" :class="selected.badgeKind">{{ selected.badge }}</em>
        </span>
        <span v-if="selected?.description && grow" class="trigger-desc">{{ selected.description }}</span>
      </span>
      <AppIcon class="trigger-chev" name="chevron" :size="12" />
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        class="toolbar-select-menu"
        :class="{ ready: menuReady }"
        :style="menuStyle"
        role="listbox"
        @pointerdown.stop
        @click.stop
        @keydown.escape="closeMenu"
      >
        <div class="menu-body">
        <section v-for="section in groupedOptions" :key="section.group || 'default'" class="menu-section">
          <p v-if="section.group" class="menu-group">{{ section.group }}</p>
          <div
            v-for="option in section.items"
            :key="String(option.value)"
            class="menu-item-wrap"
            @mouseenter="expandOption(option, $event.currentTarget)"
          >
          <button
            type="button"
            class="menu-item"
            :class="{ active: option.value === modelValue, nested: !!option.children?.length, open: expandedValue === option.value }"
            role="option"
            :aria-selected="option.value === modelValue"
            @click="onItemClick(option, $event)"
          >
            <span
              v-if="option.icon"
              class="menu-icon"
              :style="option.accent ? { '--accent': option.accent } : undefined"
            >
              <AppIcon :name="option.icon" :size="14" />
            </span>
            <span class="menu-copy">
              <span class="menu-label">
                {{ option.label }}
                <em v-if="option.badge" class="option-badge" :class="option.badgeKind">{{ option.badge }}</em>
              </span>
              <span v-if="option.description" class="menu-desc">{{ option.description }}</span>
            </span>
            <AppIcon v-if="option.children?.length" class="menu-check" name="chevron-right" :size="12" />
            <AppIcon v-else-if="option.value === modelValue" class="menu-check" name="check" :size="14" />
          </button>
          </div>
        </section>
        <p v-if="searchable && !visibleOptions.length" class="menu-empty">{{ t('chat.noMatch') }}</p>
        </div>
        <div v-if="searchable" class="menu-search">
          <AppIcon name="search" :size="13" />
          <input
            ref="searchInput"
            v-model="query"
            type="search"
            :placeholder="searchText"
            @keydown.enter.prevent="pickFirstMatch"
          />
        </div>
      </div>
      <div
        v-if="open && expandedOption"
        ref="submenuRef"
        class="toolbar-select-submenu"
        :class="{ ready: menuReady }"
        :style="submenuStyle"
        @pointerdown.stop
        @click.stop
      >
        <p class="menu-group">{{ expandedOption.label }}</p>
        <button
          v-for="child in expandedOption.children"
          :key="String(child.value)"
          type="button"
          class="menu-item"
          :class="{ active: expandedOption.value === modelValue && child.value === selectedChildValue }"
          @click="pick(expandedOption, child)"
        >
          <span class="menu-copy">
            <span class="menu-label">{{ child.label }}</span>
            <span v-if="child.description" class="menu-desc">{{ child.description }}</span>
          </span>
          <AppIcon
            v-if="expandedOption.value === modelValue && child.value === selectedChildValue"
            class="menu-check"
            name="check"
            :size="14"
          />
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.toolbar-select {
  position: relative;
  min-width: var(--select-min-w);
  flex-shrink: 0;
}
.toolbar-select.grow {
  flex: 1 1 120px;
  max-width: 240px;
}
.toolbar-select-trigger {
  width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 10px 0 8px;
  border: var(--border-width) solid transparent;
  border-radius: 999px;
  background: var(--panel-bg);
  color: var(--text-h);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;
}
.toolbar-select-trigger.placeholder {
  color: var(--text-muted);
  font-weight: 500;
}
.toolbar-select-trigger:hover,
.toolbar-select.open .toolbar-select-trigger {
  background: var(--code-bg);
  border-color: color-mix(in srgb, var(--primary) 28%, var(--border));
}
.trigger-icon,
.menu-icon {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: color-mix(in srgb, var(--accent, var(--primary)) 14%, var(--code-bg));
  color: var(--accent, var(--primary));
}
.trigger-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  text-align: left;
}
.trigger-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  line-height: 1.2;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.trigger-desc {
  font-size: 10px;
  font-weight: 500;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.trigger-chev {
  flex-shrink: 0;
  color: var(--text-muted);
  transform: rotate(-90deg);
  transition: transform 0.15s ease;
}
.toolbar-select.open .trigger-chev {
  transform: rotate(0deg);
}
.toolbar-select-menu {
  max-height: min(360px, 50vh);
  overflow: hidden;
  overflow-anchor: none;
  display: flex;
  flex-direction: column;
  padding: 6px 6px 0;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}
.menu-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-bottom: 6px;
}
.menu-search {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 -6px;
  padding: 8px 10px;
  border-top: var(--border-width) solid var(--border);
  color: var(--text-muted);
}
.menu-search input {
  flex: 1;
  min-width: 0;
  height: 28px;
  border: 0;
  background: transparent;
  color: var(--text-h);
  outline: none;
  font: inherit;
  font-size: 13px;
}
.menu-search input::-webkit-search-decoration,
.menu-search input::-webkit-search-cancel-button {
  display: none;
}
.menu-empty {
  margin: 12px 8px;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}
.toolbar-select-menu.ready {
  opacity: 1;
  pointer-events: auto;
}
html[data-theme='dark'] .toolbar-select-menu {
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.45);
}
.menu-section + .menu-section {
  margin-top: 4px;
  padding-top: 4px;
  border-top: var(--border-width) solid var(--border);
}
.menu-group {
  margin: 2px 8px 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-h);
  text-align: left;
  cursor: pointer;
  transition: background-color 0.12s ease;
}
.menu-item:hover {
  background: var(--code-bg);
}
.menu-item.active,
.menu-item.open {
  background: var(--primary-soft);
}
.toolbar-select-submenu {
  overflow: auto;
  padding: 6px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}
.toolbar-select-submenu.ready {
  opacity: 1;
  pointer-events: auto;
}
html[data-theme='dark'] .toolbar-select-submenu {
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.45);
}
.menu-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.menu-label {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.option-badge {
  font-size: 10px;
  font-style: normal;
  font-weight: 600;
  padding: 0 5px;
  border-radius: 999px;
  line-height: 1.5;
  flex-shrink: 0;
  background: var(--code-bg);
  color: var(--text-muted);
}
.option-badge.ok {
  color: #15803d;
  background: color-mix(in srgb, #22c55e 16%, var(--panel-bg));
}
.option-badge.fail {
  color: #b91c1c;
  background: color-mix(in srgb, #ef4444 14%, var(--panel-bg));
}
.option-badge.unknown {
  color: var(--text-muted);
}
.menu-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.3;
}
.menu-check {
  flex-shrink: 0;
  color: var(--primary);
}
</style>
