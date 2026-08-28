<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  anchor: DOMRect
  mode: 'to' | 'before'
  busy?: boolean
  ignoreEl?: HTMLElement | null
}>()

const emit = defineEmits<{ confirm: []; cancel: [] }>()

const { t } = useI18n()
const root = ref<HTMLElement | null>(null)
const pos = ref({ left: 0, top: 0, ready: false })

const title = computed(() =>
  props.mode === 'before' ? t('chat.rollbackBeforeTurn') : t('chat.rollbackToTurn'),
)
const summary = computed(() =>
  props.mode === 'before' ? t('chat.rollbackBeforeSummary') : t('chat.rollbackToSummary'),
)

function place() {
  const el = root.value
  if (!el) {
    pos.value = { left: props.anchor.left, top: props.anchor.bottom + 8, ready: true }
    return
  }
  const width = el.offsetWidth
  const height = el.offsetHeight
  const gap = 8
  const margin = 8
  let left = props.anchor.right - width
  left = Math.max(margin, Math.min(left, window.innerWidth - width - margin))

  const spaceBelow = window.innerHeight - props.anchor.bottom - margin
  const spaceAbove = props.anchor.top - margin
  const openUp = spaceBelow < height + gap && spaceAbove > spaceBelow
  const top = openUp
    ? Math.max(margin, props.anchor.top - height - gap)
    : Math.min(window.innerHeight - height - margin, props.anchor.bottom + gap)

  pos.value = { left, top, ready: true }
}

function onDoc(e: MouseEvent) {
  const target = e.target as Node
  if (root.value?.contains(target)) return
  if (props.ignoreEl?.contains(target)) return
  emit('cancel')
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    emit('cancel')
  }
}

watch(
  () => [props.anchor.left, props.anchor.top, props.anchor.bottom, props.anchor.right, props.mode] as const,
  async () => {
    pos.value = { ...pos.value, ready: false }
    await nextTick()
    place()
  },
)

onMounted(async () => {
  await nextTick()
  place()
  window.addEventListener('mousedown', onDoc, true)
  window.addEventListener('keydown', onKey)
  window.addEventListener('resize', place)
  window.addEventListener('scroll', place, true)
})

onBeforeUnmount(() => {
  window.removeEventListener('mousedown', onDoc, true)
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', place)
  window.removeEventListener('scroll', place, true)
})
</script>

<template>
  <div
    ref="root"
    class="rollback-popover dropdown-panel"
    :class="{ ready: pos.ready }"
    :style="{ left: `${pos.left}px`, top: `${pos.top}px` }"
    role="dialog"
    aria-modal="true"
    @mousedown.stop
    @click.stop
  >
    <h4 class="rollback-popover__title">{{ title }}</h4>
    <p class="rollback-popover__summary">{{ summary }}</p>
    <p class="rollback-popover__warn">{{ t('chat.rollbackConfirmWarning') }}</p>
    <footer class="rollback-popover__actions">
      <button type="button" class="btn btn-ghost" :disabled="busy" @click="emit('cancel')">
        {{ t('common.cancel') }}
      </button>
      <button type="button" class="btn rollback-popover__confirm" :disabled="busy" @click="emit('confirm')">
        {{ busy ? t('common.loading') : t('common.confirm') }}
      </button>
    </footer>
  </div>
</template>

<style scoped>
.rollback-popover {
  position: fixed;
  z-index: 12001;
  width: min(300px, calc(100vw - 16px));
  padding: 12px 14px;
  gap: 0;
  opacity: 0;
  pointer-events: none;
  transform: translateY(4px);
  transition: opacity 0.14s ease, transform 0.14s ease;
  border-color: color-mix(in srgb, var(--danger) 22%, var(--border));
}
.rollback-popover.ready {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}
.rollback-popover__title {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
  line-height: 1.35;
}
.rollback-popover__summary {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--text);
}
.rollback-popover__warn {
  margin: 8px 0 0;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--danger) 8%, var(--panel-bg));
  border: var(--border-width) solid color-mix(in srgb, var(--danger) 18%, var(--border));
  font-size: 11.5px;
  line-height: 1.45;
  color: color-mix(in srgb, var(--danger) 72%, var(--text));
}
.rollback-popover__actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 12px;
}
.rollback-popover__confirm {
  height: var(--ghost-btn-height);
  padding: 0 10px;
  border: 0;
  border-radius: var(--ghost-btn-radius);
  background: var(--danger);
  color: #fff;
  font-size: var(--ghost-btn-font-size);
  font-weight: 600;
  cursor: pointer;
}
.rollback-popover__confirm:hover:not(:disabled) {
  opacity: 0.9;
}
.rollback-popover__confirm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
