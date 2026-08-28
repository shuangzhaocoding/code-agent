<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import type { ChatMessage } from '@/protocol/applyEvent'
import AppIcon from '@/components/AppIcon.vue'
import RollbackConfirmPopover from '@/components/RollbackConfirmPopover.vue'

import type { RollbackMode } from '@/utils/rollback'
import { hasRollbackTrailing } from '@/utils/rollback'

const props = defineProps<{
  message: ChatMessage
}>()

const { t } = useI18n()
const store = useAppStore()

const trigger = ref<HTMLButtonElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const menuOpen = ref(false)
const menuReady = ref(false)
const menuStyle = ref<Record<string, string>>({})
const confirmMode = ref<RollbackMode | null>(null)
const confirmAnchor = ref<DOMRect | null>(null)
const busy = ref(false)

const canRollbackTo = computed(() => hasRollbackTrailing(props.message, store.messages, 'to'))
const canRollbackBefore = computed(() => hasRollbackTrailing(props.message, store.messages, 'before'))

function updateMenuPosition() {
  const el = trigger.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const width = 220
  const gap = 6
  let left = rect.right - width
  left = Math.max(8, Math.min(left, window.innerWidth - width - 8))

  const spaceBelow = window.innerHeight - rect.bottom - 8
  const spaceAbove = rect.top - 8
  const openUp = spaceBelow < 120 && spaceAbove > spaceBelow
  const maxHeight = Math.min(240, Math.max(96, (openUp ? spaceAbove : spaceBelow) - gap))

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

function bindLayout() {
  layoutCleanup?.()
  const onMove = () => updateMenuPosition()
  window.addEventListener('resize', onMove)
  window.addEventListener('scroll', onMove, true)
  layoutCleanup = () => {
    window.removeEventListener('resize', onMove)
    window.removeEventListener('scroll', onMove, true)
    layoutCleanup = null
  }
}

async function openMenu() {
  updateMenuPosition()
  menuReady.value = false
  menuOpen.value = true
  await nextTick()
  requestAnimationFrame(() => {
    updateMenuPosition()
    menuReady.value = true
    bindLayout()
  })
}

function closeMenu() {
  menuOpen.value = false
  menuReady.value = false
  layoutCleanup?.()
}

function toggleMenu() {
  if (busy.value) return
  if (menuOpen.value) closeMenu()
  else void openMenu()
}

function pickMode(mode: RollbackMode) {
  if (mode === 'to' && !canRollbackTo.value) return
  if (mode === 'before' && !canRollbackBefore.value) return
  const el = trigger.value
  if (!el) return
  confirmAnchor.value = el.getBoundingClientRect()
  confirmMode.value = mode
  closeMenu()
}

function closeConfirm() {
  confirmMode.value = null
  confirmAnchor.value = null
}

async function confirmRollback() {
  if (!confirmMode.value || busy.value) return
  const mode = confirmMode.value
  closeConfirm()
  busy.value = true
  try {
    await store.rollbackToMessage(props.message.id, mode)
  } catch (err) {
    const message = err instanceof Error ? err.message : t('chat.rollbackFailed')
    window.alert(message)
  } finally {
    busy.value = false
  }
}

function onDocPointer(e: PointerEvent) {
  const target = e.target as Node
  if (trigger.value?.contains(target) || menuRef.value?.contains(target)) return
  closeMenu()
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (confirmMode.value) closeConfirm()
    else closeMenu()
  }
}

watch(menuOpen, (open) => {
  if (!open) layoutCleanup?.()
})

onMounted(() => {
  document.addEventListener('pointerdown', onDocPointer)
  window.addEventListener('keydown', onKey)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointer)
  window.removeEventListener('keydown', onKey)
  layoutCleanup?.()
})
</script>

<template>
  <div class="rollback-control">
    <button
      ref="trigger"
      type="button"
      class="ghost-icon-btn rollback-trigger"
      :class="{ open: menuOpen, busy }"
      :title="t('chat.rollbackMenuTitle')"
      :aria-expanded="menuOpen"
      aria-haspopup="menu"
      :disabled="busy"
      @click="toggleMenu"
    >
      <AppIcon name="history" :size="16" :stroke-width="1.75" />
    </button>

    <Teleport to="body">
      <div
        v-if="menuOpen"
        ref="menuRef"
        class="rollback-menu dropdown-panel"
        :class="{ ready: menuReady }"
        :style="menuStyle"
        role="menu"
        @pointerdown.stop
        @click.stop
      >
        <button
          type="button"
          class="menu-item"
          role="menuitem"
          :disabled="!canRollbackTo"
          :title="canRollbackTo ? t('chat.rollbackToTurnHint') : t('chat.rollbackToTurnDisabled')"
          @click="pickMode('to')"
        >
          <AppIcon name="history" :size="16" :stroke-width="1.75" />
          <span>{{ t('chat.rollbackToTurn') }}</span>
        </button>
        <button
          type="button"
          class="menu-item"
          role="menuitem"
          :disabled="!canRollbackBefore"
          :title="t('chat.rollbackBeforeTurnHint')"
          @click="pickMode('before')"
        >
          <AppIcon name="arrow-left" :size="16" :stroke-width="1.75" />
          <span>{{ t('chat.rollbackBeforeTurn') }}</span>
        </button>
      </div>

      <RollbackConfirmPopover
        v-if="confirmMode && confirmAnchor"
        :mode="confirmMode"
        :anchor="confirmAnchor"
        :ignore-el="trigger"
        :busy="busy"
        @confirm="confirmRollback"
        @cancel="closeConfirm"
      />
    </Teleport>
  </div>
</template>

<style scoped>
.rollback-control {
  display: inline-flex;
}
.rollback-trigger.open {
  opacity: 1;
  color: var(--primary);
}
.rollback-trigger.busy {
  opacity: 0.5;
  cursor: wait;
}
.rollback-menu {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
  overflow: auto;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}
.rollback-menu.ready {
  opacity: 1;
  pointer-events: auto;
}
.rollback-menu .menu-item {
  width: 100%;
}
.rollback-menu .menu-item:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
