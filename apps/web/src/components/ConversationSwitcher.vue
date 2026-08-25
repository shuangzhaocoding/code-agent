<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import { useSessionPins } from '@/composables/useSessionPins'
import { formatRelativeTime } from '@/utils/relativeTime'

const store = useAppStore()
const pins = useSessionPins()
const open = ref(false)
const ready = ref(false)
const query = ref('')
const active = ref(0)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const searchEl = ref<HTMLInputElement | null>(null)
const menuStyle = ref<Record<string, string>>({})

const current = computed(() =>
  store.conversations.find((c) => c.id === store.conversationId) || null,
)

const currentTitle = computed(() => current.value?.title || '新会话')

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const matched = q
    ? store.conversations.filter((c) => c.title.toLowerCase().includes(q))
    : store.conversations
  return pins.sortByPin(matched)
})

const pinnedItems = computed(() => filtered.value.filter((c) => pins.isPinned(c.id)))
const recentItems = computed(() => filtered.value.filter((c) => !pins.isPinned(c.id)))

const sections = computed(() => {
  const rows: { label: string; items: typeof filtered.value }[] = []
  if (pinnedItems.value.length) rows.push({ label: '置顶', items: pinnedItems.value })
  if (recentItems.value.length) rows.push({ label: query.value.trim() ? '匹配' : '最近', items: recentItems.value })
  return rows
})

function updateMenuPosition() {
  const el = trigger.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const width = Math.min(Math.max(rect.width + 40, 320), Math.min(420, window.innerWidth - 16))
  let left = rect.left
  if (left + width > window.innerWidth - 8) left = window.innerWidth - width - 8
  left = Math.max(8, left)

  const gap = 6
  const spaceBelow = window.innerHeight - rect.bottom - 8
  const spaceAbove = rect.top - 8
  const openUp = spaceBelow < 240 && spaceAbove > spaceBelow
  const available = (openUp ? spaceAbove : spaceBelow) - gap
  const maxHeight = Math.min(440, Math.max(120, available))

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
  query.value = ''
  active.value = Math.max(0, filtered.value.findIndex((c) => c.id === store.conversationId))
  updateMenuPosition()
  ready.value = false
  open.value = true
  await nextTick()
  requestAnimationFrame(() => {
    updateMenuPosition()
    ready.value = true
    bindLayout()
    searchEl.value?.focus()
  })
}

function closeMenu() {
  open.value = false
  ready.value = false
  query.value = ''
  layoutCleanup?.()
}

function toggleMenu() {
  if (open.value) closeMenu()
  else void openMenu()
}

async function pick(id: string) {
  closeMenu()
  if (id === store.conversationId) return
  await store.openConversation(id)
}

async function startNew() {
  closeMenu()
  await store.newChat()
}

function onTogglePin(id: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  pins.toggle(id)
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
  if (!filtered.value.length) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    active.value = (active.value + 1) % filtered.value.length
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    active.value = (active.value - 1 + filtered.value.length) % filtered.value.length
    return
  }
  if (e.key === 'Enter') {
    const item = filtered.value[active.value]
    if (item) {
      e.preventDefault()
      void pick(item.id)
    }
  }
}

watch(filtered, (list) => {
  if (active.value >= list.length) active.value = Math.max(0, list.length - 1)
})

watch(active, async () => {
  if (!open.value) return
  await nextTick()
  menuRef.value?.querySelector<HTMLElement>('.session-row.active')?.scrollIntoView({ block: 'nearest' })
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
  <header class="session-switcher">
    <div ref="root" class="switcher-main" :class="{ open }">
      <button
        ref="trigger"
        type="button"
        class="switcher-trigger"
        :aria-expanded="open"
        aria-haspopup="listbox"
        :title="currentTitle"
        @click="toggleMenu"
      >
        <span class="switcher-icon">
          <AppIcon name="chat" :size="14" />
        </span>
        <span class="switcher-copy">
          <span class="switcher-title">{{ currentTitle }}</span>
        </span>
        <AppIcon class="switcher-chev" name="chevron" :size="13" />
      </button>

      <Teleport to="body">
        <div
          v-if="open"
          ref="menuRef"
          class="switcher-menu"
          :class="{ ready }"
          :style="menuStyle"
          role="listbox"
          @pointerdown.stop
        >
          <div class="switcher-search">
            <AppIcon name="search" :size="14" />
            <input
              ref="searchEl"
              v-model="query"
              type="search"
              placeholder="搜索会话"
              autocomplete="off"
              spellcheck="false"
            />
          </div>

          <div class="switcher-list">
            <p v-if="!filtered.length" class="switcher-empty">
              {{ store.conversations.length ? '没有匹配的会话' : '暂无历史会话' }}
            </p>
            <section v-for="section in sections" :key="section.label">
              <h2>{{ section.label }}</h2>
              <div
                v-for="item in section.items"
                :key="item.id"
                class="session-row"
                :class="{
                  active: item.id === filtered[active]?.id,
                  current: item.id === store.conversationId,
                }"
                role="option"
                :aria-selected="item.id === store.conversationId"
                @mouseenter="active = filtered.findIndex((row) => row.id === item.id)"
                @click="pick(item.id)"
              >
                <span class="row-icon">
                  <AppIcon name="chat" :size="13" />
                </span>
                <span class="row-copy">
                  <span class="row-title">{{ item.title }}</span>
                  <span v-if="item.updated_at || item.created_at" class="row-time">
                    {{ formatRelativeTime(item.updated_at || item.created_at) }}
                  </span>
                </span>
                <button
                  type="button"
                  class="row-pin"
                  :class="{ on: pins.isPinned(item.id) }"
                  :title="pins.isPinned(item.id) ? '取消置顶' : '置顶'"
                  @click="onTogglePin(item.id, $event)"
                >
                  <AppIcon name="pin" :size="12" />
                </button>
                <AppIcon v-if="item.id === store.conversationId" class="row-check" name="check" :size="14" />
              </div>
            </section>
          </div>
        </div>
      </Teleport>
    </div>

    <button type="button" class="switcher-new" title="新会话" @click="startNew">
      <AppIcon name="plus" :size="15" />
    </button>
  </header>
</template>

<style scoped>
.session-switcher {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 40px;
  padding: 0 10px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--panel-bg);
  flex-shrink: 0;
}
.switcher-main {
  min-width: 0;
  flex: 1;
}
.switcher-trigger {
  width: 100%;
  height: 30px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 8px 0 4px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-h);
  text-align: left;
  cursor: pointer;
}
.switcher-trigger:hover,
.switcher-main.open .switcher-trigger {
  background: var(--code-bg);
}
.switcher-icon,
.row-icon {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: var(--primary-soft);
  color: var(--primary);
}
.switcher-copy {
  min-width: 0;
  flex: 1;
}
.switcher-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}
.row-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.row-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}
.row-time {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-muted);
}
.switcher-chev {
  flex-shrink: 0;
  color: var(--text-muted);
  transition: transform 0.15s ease;
}
.switcher-main.open .switcher-chev {
  transform: rotate(180deg);
}
.switcher-new {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  display: grid;
  place-items: center;
  cursor: pointer;
}
.switcher-new:hover {
  background: var(--primary-soft);
  color: var(--primary);
}
.switcher-menu {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: var(--border-width) solid var(--border-strong);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}
.switcher-menu.ready {
  opacity: 1;
  pointer-events: auto;
}
html[data-theme='dark'] .switcher-menu {
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.45);
}
.switcher-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 8px 4px;
  padding: 0 10px;
  height: 32px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--code-bg);
  color: var(--text-muted);
  flex-shrink: 0;
}
.switcher-search:focus-within {
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
}
.switcher-search input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-h);
  outline: none;
  font-size: 13px;
}
.switcher-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px 6px 8px;
}
.switcher-list h2 {
  margin: 8px 8px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.switcher-list section:first-child h2 {
  margin-top: 4px;
}
.switcher-empty {
  margin: 20px 8px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}
.session-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-h);
  text-align: left;
  cursor: pointer;
  font: inherit;
}
.session-row:hover,
.session-row.active {
  background: var(--code-bg);
}
.session-row.current {
  background: var(--primary-soft);
}
.session-row.current .row-title {
  color: var(--primary);
}
.row-pin {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  display: grid;
  place-items: center;
  opacity: 0;
  cursor: pointer;
}
.session-row:hover .row-pin,
.session-row.active .row-pin,
.row-pin.on {
  opacity: 1;
}
.row-pin:hover,
.row-pin.on {
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 10%, transparent);
}
.row-check {
  flex-shrink: 0;
  color: var(--primary);
}
</style>
