<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'

export type FormSelectOption = {
  value: string
  label: string
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    options: FormSelectOption[]
    placeholder?: string
    id?: string
    disabled?: boolean
  }>(),
  {
    placeholder: '',
    id: undefined,
    disabled: false,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { t } = useI18n()
const open = ref(false)
const ready = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const menuStyle = ref<Record<string, string>>({})

const placeholderText = computed(() => props.placeholder || t('common.select'))
const selected = computed(() => props.options.find((o) => o.value === props.modelValue))
const displayLabel = computed(() => selected.value?.label || placeholderText.value)

function updateMenuPosition() {
  const el = trigger.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const width = rect.width
  const gap = 4
  const spaceBelow = window.innerHeight - rect.bottom - 8
  const spaceAbove = rect.top - 8
  const openUp = spaceBelow < 160 && spaceAbove > spaceBelow
  const maxHeight = Math.min(280, Math.max(120, (openUp ? spaceAbove : spaceBelow) - gap))

  menuStyle.value = {
    position: 'fixed',
    left: `${rect.left}px`,
    width: `${width}px`,
    maxHeight: `${maxHeight}px`,
    zIndex: '12000',
    ...(openUp
      ? { top: 'auto', bottom: `${window.innerHeight - rect.top + gap}px` }
      : { top: `${rect.bottom + gap}px`, bottom: 'auto' }),
  }
}

let layoutCleanup: (() => void) | null = null
let positionRaf = 0

function schedulePosition() {
  if (positionRaf) return
  positionRaf = requestAnimationFrame(() => {
    positionRaf = 0
    if (open.value) updateMenuPosition()
  })
}

function bindLayout() {
  layoutCleanup?.()
  const onMove = () => schedulePosition()
  window.addEventListener('resize', onMove)
  window.addEventListener('scroll', onMove, true)
  layoutCleanup = () => {
    window.removeEventListener('resize', onMove)
    window.removeEventListener('scroll', onMove, true)
    layoutCleanup = null
  }
}

async function openMenu() {
  if (props.disabled) return
  updateMenuPosition()
  ready.value = false
  open.value = true
  await nextTick()
  requestAnimationFrame(() => {
    updateMenuPosition()
    ready.value = true
    bindLayout()
  })
}

function closeMenu() {
  open.value = false
  ready.value = false
  layoutCleanup?.()
}

function toggleMenu() {
  if (open.value) closeMenu()
  else void openMenu()
}

function pick(value: string) {
  emit('update:modelValue', value)
  closeMenu()
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
  document.addEventListener('pointerdown', onDocPointer)
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointer)
  window.removeEventListener('keydown', onKey)
  layoutCleanup?.()
  if (positionRaf) cancelAnimationFrame(positionRaf)
})
</script>

<template>
  <div ref="root" class="form-select" :class="{ open, disabled }">
    <button
      :id="id"
      ref="trigger"
      type="button"
      class="form-select-trigger"
      :class="{ placeholder: !selected }"
      :aria-expanded="open"
      aria-haspopup="listbox"
      :disabled="disabled"
      @click="toggleMenu"
    >
      <span class="trigger-label">{{ displayLabel }}</span>
      <AppIcon class="trigger-chev" name="chevron" :size="16" :stroke-width="1.75" />
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        class="form-select-menu"
        :class="{ ready }"
        :style="menuStyle"
        role="listbox"
        @pointerdown.stop
      >
        <button
          v-for="option in options"
          :key="option.value"
          type="button"
          class="menu-item"
          :class="{ active: option.value === modelValue }"
          role="option"
          :aria-selected="option.value === modelValue"
          @click="pick(option.value)"
        >
          <span class="menu-label">{{ option.label }}</span>
          <AppIcon v-if="option.value === modelValue" class="menu-check" name="check" :size="16" :stroke-width="1.75" />
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.form-select {
  position: relative;
  width: 100%;
  min-width: 0;
}
.form-select-trigger {
  width: 100%;
  min-height: 30px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px 0 12px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--code-bg);
  color: var(--text-h);
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease,
    box-shadow 0.15s ease;
}
.form-select-trigger.placeholder {
  color: var(--text-muted);
}
.form-select-trigger:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  background: var(--panel-bg);
}
.form-select.open .form-select-trigger,
.form-select-trigger:focus-visible {
  outline: none;
  border-color: var(--primary);
  background: var(--panel-bg);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 16%, transparent);
}
.form-select.disabled .form-select-trigger {
  opacity: 0.55;
  cursor: not-allowed;
}
.trigger-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.trigger-chev {
  flex-shrink: 0;
  color: var(--text-muted);
  transition: transform 0.15s ease;
}
.form-select.open .trigger-chev {
  transform: rotate(180deg);
}
.form-select-menu {
  display: flex;
  flex-direction: column;
  overflow: auto;
  gap: 2px;
  padding: 6px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: var(--dropdown-shadow);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}
.form-select-menu.ready {
  opacity: 1;
  pointer-events: auto;
}
html[data-theme='dark'] .form-select-menu {
  box-shadow: var(--dropdown-shadow-dark);
}
.form-select-menu .menu-item {
  width: 100%;
}
.form-select-menu .menu-item.active {
  color: var(--text-h);
  font-weight: 500;
}
.menu-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.menu-check {
  flex-shrink: 0;
  color: var(--primary);
}
</style>
