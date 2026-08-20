<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'

export type ContextMenuItem = {
  id: string
  label?: string
  icon?: string
  danger?: boolean
  disabled?: boolean
  separator?: boolean
}

const props = defineProps<{
  x: number
  y: number
  items: ContextMenuItem[]
}>()

const emit = defineEmits<{
  select: [id: string]
  close: []
}>()

const root = ref<HTMLElement | null>(null)
const pos = ref({ left: props.x, top: props.y })

const visibleItems = computed(() => props.items)

function onSelect(item: ContextMenuItem) {
  if (item.separator || item.disabled) return
  emit('select', item.id)
  emit('close')
}

function place() {
  const el = root.value
  if (!el) {
    pos.value = { left: props.x, top: props.y }
    return
  }
  const w = el.offsetWidth
  const h = el.offsetHeight
  pos.value = {
    left: Math.min(props.x, window.innerWidth - w - 8),
    top: Math.min(props.y, window.innerHeight - h - 8),
  }
}

function onDoc(e: MouseEvent) {
  if (root.value?.contains(e.target as Node)) return
  emit('close')
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

watch(
  () => [props.x, props.y, props.items.length] as const,
  async () => {
    pos.value = { left: props.x, top: props.y }
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
})

onBeforeUnmount(() => {
  window.removeEventListener('mousedown', onDoc, true)
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', place)
})
</script>

<template>
  <div
    ref="root"
    class="ctx"
    :style="{ left: pos.left + 'px', top: pos.top + 'px' }"
    @click.stop
    @contextmenu.prevent
  >
    <template v-for="item in visibleItems" :key="item.id">
      <div v-if="item.separator" class="ctx-sep" />
      <button
        v-else
        type="button"
        :class="{ danger: item.danger }"
        :disabled="item.disabled"
        @click="onSelect(item)"
      >
        <AppIcon v-if="item.icon" class="ctx-ico" :name="item.icon" :size="15" />
        <span>{{ item.label }}</span>
      </button>
    </template>
  </div>
</template>

<style scoped>
.ctx {
  position: fixed;
  z-index: 80;
  min-width: 168px;
  padding: 6px;
  background: var(--bg-elevated);
  border: var(--border-width) solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-md);
  display: flex;
  flex-direction: column;
}
.ctx-sep {
  height: 1px;
  margin: 4px 6px;
  background: var(--border);
}
.ctx button {
  display: flex;
  align-items: center;
  gap: 8px;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--text);
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  line-height: 1.3;
}
.ctx-ico {
  flex: 0 0 16px;
  width: 16px;
  color: color-mix(in srgb, var(--text) 62%, transparent);
}
.ctx button:hover:not(:disabled) { background: var(--bg-muted); color: var(--text-h); }
.ctx button:hover:not(:disabled) .ctx-ico { color: var(--text-h); }
.ctx button:disabled {
  opacity: 0.4;
  cursor: default;
}
.ctx button.danger { color: var(--danger); }
.ctx button.danger .ctx-ico { color: var(--danger); }
</style>
