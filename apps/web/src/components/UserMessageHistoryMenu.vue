<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'

export type UserHistoryEntry = { id: string; preview: string; time: string }

const props = defineProps<{
  entries: UserHistoryEntry[]
  activeId: string | null
}>()

const emit = defineEmits<{
  select: [id: string]
  edit: [id: string]
  copy: [id: string]
}>()

const { t } = useI18n()
const open = ref(false)
const ready = ref(false)
const active = ref(0)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const menuStyle = ref<Record<string, string>>({})

function updateMenuPosition() {
  const el = trigger.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const width = Math.min(360, window.innerWidth - 16)
  let left = rect.right - width
  left = Math.max(8, Math.min(left, window.innerWidth - width - 8))

  const gap = 6
  const spaceBelow = window.innerHeight - rect.bottom - 8
  const spaceAbove = rect.top - 8
  const openUp = spaceBelow < 200 && spaceAbove > spaceBelow
  const available = (openUp ? spaceAbove : spaceBelow) - gap
  const maxHeight = Math.min(400, Math.max(120, available))

  menuStyle.value = {
    position: 'fixed',
    left: `${left}px`,
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
  if (!props.entries.length) return
  active.value = Math.max(0, props.entries.findIndex((e) => e.id === props.activeId))
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

function pick(id: string) {
  closeMenu()
  emit('select', id)
}

function onEdit(id: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  closeMenu()
  emit('edit', id)
}

function onCopy(id: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  emit('copy', id)
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
    return
  }
  if (!props.entries.length) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    active.value = (active.value + 1) % props.entries.length
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    active.value = (active.value - 1 + props.entries.length) % props.entries.length
    return
  }
  if (e.key === 'Enter') {
    const item = props.entries[active.value]
    if (item) {
      e.preventDefault()
      pick(item.id)
    }
  }
}

watch(
  () => props.entries.length,
  (len) => {
    if (active.value >= len) active.value = Math.max(0, len - 1)
    if (!len) closeMenu()
  },
)

watch(active, async () => {
  if (!open.value) return
  await nextTick()
  menuRef.value?.querySelector<HTMLElement>('.history-item.active')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
})

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
  <div ref="root" class="history-menu-root" :class="{ open, disabled: !entries.length }">
    <button
      ref="trigger"
      type="button"
      class="ghost-icon-btn"
      :class="{ active: open }"
      :aria-expanded="open"
      aria-haspopup="listbox"
      :title="t('chat.userHistory')"
      :disabled="!entries.length"
      @click="toggleMenu"
    >
      <AppIcon name="history" :size="16" :stroke-width="1.75" />
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        class="history-menu dropdown-panel"
        :class="{ ready }"
        :style="menuStyle"
        role="listbox"
        :aria-label="t('chat.userHistory')"
        @pointerdown.stop
      >
        <div class="history-menu-head">{{ t('chat.userHistory') }}</div>
        <ol class="history-list">
          <li
            v-for="(entry, index) in entries"
            :key="entry.id"
            class="history-item"
            :class="{ active: index === active, current: entry.id === activeId }"
            @mouseenter="active = index"
          >
            <button
              type="button"
              class="history-row"
              role="option"
              :aria-selected="entry.id === activeId"
              @click="pick(entry.id)"
            >
              <span class="history-index">{{ index + 1 }}</span>
              <span class="history-body">
                <span class="history-time">{{ entry.time }}</span>
                <span class="history-preview">{{ entry.preview }}</span>
              </span>
            </button>
            <div class="history-actions">
              <button
                type="button"
                class="ghost-icon-btn history-action-btn"
                :title="t('common.edit')"
                @click="onEdit(entry.id, $event)"
              >
                <AppIcon name="pencil" :size="16" :stroke-width="1.75" />
              </button>
              <button
                type="button"
                class="ghost-icon-btn history-action-btn"
                :title="t('common.copy')"
                @click="onCopy(entry.id, $event)"
              >
                <AppIcon name="copy" :size="16" :stroke-width="1.75" />
              </button>
            </div>
          </li>
        </ol>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.history-menu-root {
  flex-shrink: 0;
}
.history-menu {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  gap: 0;
  padding: 0;
}
.history-menu-head {
  flex-shrink: 0;
  padding: 8px 10px 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
  border-bottom: var(--border-width) solid var(--border);
}
.history-list {
  list-style: none;
  margin: 0;
  padding: 6px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.history-item {
  display: flex;
  align-items: flex-start;
  gap: 2px;
  min-height: 34px;
  border-radius: var(--radius-sm);
  transition: background-color 0.12s ease;
}
.history-item:hover,
.history-item.active {
  background: var(--code-bg);
}
.history-item.current {
  background: var(--code-bg);
}
.history-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex: 1;
  min-width: 0;
  padding: 4px 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  text-align: left;
  cursor: pointer;
  color: inherit;
  font: inherit;
}
.history-actions {
  display: flex;
  gap: 0;
  flex-shrink: 0;
  padding: 0 4px 0 0;
  opacity: 0;
  transition: opacity 0.12s ease;
}
.history-item:hover .history-actions,
.history-item.active .history-actions,
.history-item.current .history-actions {
  opacity: 1;
}
.history-action-btn {
  opacity: 1;
}
.history-index {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 10px;
  font-family: var(--mono);
  color: var(--text-secondary);
  background: var(--border);
}
.history-row.current .history-index,
.history-item.active .history-index,
.history-item.current .history-index {
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 18%, transparent);
}
.history-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.history-time {
  font-size: 10px;
  font-family: var(--mono);
  color: var(--text-secondary);
}
.history-preview {
  font-size: 12px;
  line-height: 1.35;
  color: var(--text-h);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.history-row.current .history-preview,
.history-item.current .history-preview {
  color: var(--primary);
}
</style>
