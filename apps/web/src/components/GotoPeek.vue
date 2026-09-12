<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { t } from '@/i18n'

export type GotoHit = {
  path: string
  line: number
  text: string
  kind?: string
}

const props = defineProps<{
  hits: GotoHit[]
  active: number
  left: number
  top: number
  symbol: string
}>()

const emit = defineEmits<{
  'update:active': [value: number]
  pick: [hit: GotoHit]
  close: []
}>()

const rootEl = ref<HTMLElement | null>(null)

watch(
  () => props.hits,
  async () => {
    await nextTick()
    rootEl.value?.focus()
  },
  { immediate: true },
)

const items = computed(() => props.hits)

function fileName(path: string) {
  return path.split('/').pop() || path
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    emit('update:active', Math.min(props.active + 1, items.value.length - 1))
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    emit('update:active', Math.max(props.active - 1, 0))
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    const hit = items.value[props.active]
    if (hit) emit('pick', hit)
  }
}
</script>

<template>
  <div
    ref="rootEl"
    class="goto-peek"
    :style="{ left: `${left}px`, top: `${top}px` }"
    tabindex="0"
    role="listbox"
    :aria-label="t('editor.gotoPeek', { symbol })"
    @keydown="onKey"
    @mousedown.stop
  >
    <header>{{ t('editor.gotoPeek', { symbol }) }}</header>
    <button
      v-for="(hit, i) in items"
      :key="`${hit.path}:${hit.line}`"
      type="button"
      class="hit"
      :class="{ active: i === active }"
      role="option"
      :aria-selected="i === active"
      @mouseenter="emit('update:active', i)"
      @click="emit('pick', hit)"
    >
      <AppIcon name="file" :size="13" />
      <span class="copy">
        <span class="name">{{ fileName(hit.path) }}:{{ hit.line }}</span>
        <small>{{ hit.text }}</small>
      </span>
    </button>
  </div>
</template>

<style scoped>
.goto-peek {
  position: absolute;
  z-index: 21;
  width: min(420px, calc(100% - 24px));
  max-height: 240px;
  overflow: auto;
  border: var(--border-width) solid var(--border);
  border-radius: 10px;
  background: var(--panel-bg);
  box-shadow: 0 12px 32px color-mix(in srgb, #000 28%, transparent);
  outline: none;
}
.goto-peek header {
  padding: 8px 12px 4px;
  font-size: 11px;
  font-weight: 650;
  color: var(--text-muted);
}
.hit {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  padding: 6px 12px;
  border: 0;
  background: transparent;
  color: var(--text-h);
  text-align: left;
  cursor: pointer;
}
.hit.active {
  background: color-mix(in srgb, var(--primary) 14%, transparent);
}
.copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}
.name {
  font-size: 12.5px;
  font-weight: 600;
}
small {
  font-size: 11px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
