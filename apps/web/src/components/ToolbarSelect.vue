<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import type { AppIconName } from '@/components/AppIcon.vue'

export type ToolbarSelectOption = {
  value: string | null
  label: string
  description?: string
  icon?: AppIconName | string
  accent?: string
  group?: string
}

const props = withDefaults(
  defineProps<{
    modelValue: string | null
    options: ToolbarSelectOption[]
    placeholder?: string
    minWidth?: number
    grow?: boolean
  }>(),
  {
    placeholder: '请选择',
    minWidth: 96,
    grow: false,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>()

const open = ref(false)
const menuReady = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const menuStyle = ref<Record<string, string>>({})

const selected = computed(() => props.options.find((o) => o.value === props.modelValue))

const groupedOptions = computed(() => {
  const hasGroup = props.options.some((o) => o.group)
  if (!hasGroup) return [{ group: '', items: props.options }]
  const map = new Map<string, ToolbarSelectOption[]>()
  for (const option of props.options) {
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

function schedulePositionUpdate() {
  if (positionRaf) return
  positionRaf = requestAnimationFrame(() => {
    positionRaf = 0
    if (open.value) updateMenuPosition()
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

function openMenu() {
  updateMenuPosition()
  menuReady.value = false
  open.value = true
  requestAnimationFrame(() => {
    updateMenuPosition()
    menuReady.value = true
    bindLayoutListeners()
  })
}

function closeMenu() {
  open.value = false
  menuReady.value = false
  layoutCleanup?.()
}

function toggleMenu() {
  if (open.value) closeMenu()
  else openMenu()
}

function pick(value: string | null) {
  emit('update:modelValue', value)
  closeMenu()
}

function onDocPointer(e: PointerEvent) {
  const target = e.target as Node
  if (root.value?.contains(target) || menuRef.value?.contains(target)) return
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
        <span class="trigger-label">{{ selected?.label || placeholder }}</span>
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
      >
        <section v-for="section in groupedOptions" :key="section.group || 'default'" class="menu-section">
          <p v-if="section.group" class="menu-group">{{ section.group }}</p>
          <button
            v-for="option in section.items"
            :key="String(option.value)"
            type="button"
            class="menu-item"
            :class="{ active: option.value === modelValue }"
            role="option"
            :aria-selected="option.value === modelValue"
            @click="pick(option.value)"
          >
            <span
              v-if="option.icon"
              class="menu-icon"
              :style="option.accent ? { '--accent': option.accent } : undefined"
            >
              <AppIcon :name="option.icon" :size="14" />
            </span>
            <span class="menu-copy">
              <span class="menu-label">{{ option.label }}</span>
              <span v-if="option.description" class="menu-desc">{{ option.description }}</span>
            </span>
            <AppIcon v-if="option.value === modelValue" class="menu-check" name="check" :size="14" />
          </button>
        </section>
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
  max-height: min(320px, 50vh);
  overflow: auto;
  overflow-anchor: none;
  contain: layout style paint;
  padding: 6px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
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
.menu-item.active {
  background: var(--primary-soft);
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
