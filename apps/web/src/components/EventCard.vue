<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'

const props = withDefaults(
  defineProps<{
    icon: string
    title: string
    subtitle?: string
    tone?: 'default' | 'think' | 'danger' | 'tool'
    status?: string
    defaultOpen?: boolean
    activatable?: boolean
  }>(),
  { tone: 'default', defaultOpen: false, subtitle: '', status: '', activatable: false },
)

const emit = defineEmits<{ activate: [] }>()
const open = ref(props.defaultOpen || props.status === 'streaming')

watch(
  () => props.status,
  (status, prev) => {
    if (status === 'streaming') {
      open.value = true
      return
    }
    if (prev === 'streaming' && status !== 'error') {
      open.value = false
    }
  },
)

const collapsed = computed(() => !open.value)

function toggle() {
  open.value = !open.value
}

function onHeadClick() {
  const next = !open.value
  open.value = next
  if (props.activatable && next) emit('activate')
}

function onChevron(e: Event) {
  e.preventDefault()
  e.stopPropagation()
  toggle()
}
</script>

<template>
  <div class="card" :class="[tone, status, { open, collapsed }]">
    <div class="row">
      <div class="head" :class="{ activatable }" @click="onHeadClick">
        <span class="glyph" aria-hidden="true">
          <AppIcon :name="icon" :size="13" />
        </span>
        <span class="titles">
          <span class="title" :class="{ running: status === 'streaming' }">{{ title }}</span>
          <span v-if="subtitle" class="sub">{{ subtitle }}</span>
        </span>
        <span v-if="status === 'error'" class="pill error">失败</span>
        <button type="button" class="chev-btn" @click="onChevron">
          <AppIcon class="chev" name="chevron" :size="13" />
        </button>
      </div>
      <div v-show="open" class="body">
        <slot />
      </div>
    </div>
    <div v-if="$slots.footer" class="foot">
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.card {
  margin: 3px 0;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  overflow: clip;
  overflow-anchor: none;
  contain: layout style;
}
.card.collapsed {
  background: transparent;
  border-color: transparent;
}
.card.collapsed:hover {
  border-color: var(--border);
  background: color-mix(in srgb, var(--code-bg) 50%, transparent);
}
.row {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  min-width: 0;
}
.head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 5px 8px;
  border: 0;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  min-width: 0;
  width: 100%;
}
.card.open .head {
  background: color-mix(in srgb, var(--code-bg) 60%, var(--panel-bg));
  border-bottom: var(--border-width) solid var(--border);
}
.card.error { border-color: color-mix(in srgb, var(--danger) 34%, var(--border)); }
.head:hover { background: var(--code-bg); }
.head.activatable .titles { cursor: pointer; }
.head.activatable .sub { color: var(--primary); }
.glyph {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: var(--code-bg);
  color: var(--text-secondary);
}
.think .glyph {
  color: var(--traj-think);
  background: var(--traj-think-soft);
}
.danger .glyph {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 14%, var(--code-bg));
}
.tool .glyph {
  color: var(--traj-tool);
  background: var(--traj-tool-soft);
}
.default .glyph {
  color: var(--traj-context);
  background: var(--traj-context-soft);
}
.titles {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: row;
  align-items: baseline;
  gap: 8px;
  min-height: 18px;
}
.title {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  color: var(--text-h);
}
.title.running {
  animation: title-pulse 1.2s ease-in-out infinite;
}
.sub {
  min-width: 0;
  flex: 1;
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pill {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--code-bg);
}
.pill.error {
  color: var(--error-text);
  background: color-mix(in srgb, var(--error-text) 12%, var(--panel-bg));
}
.chev-btn {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
}
.chev-btn:hover { background: var(--code-bg); color: var(--text); }
.chev { transition: transform 0.16s ease; transform: rotate(-90deg); }
.open .chev { transform: rotate(0deg); }
.body {
  flex: 1;
  min-width: 0;
  padding: 8px 10px 10px;
  background: var(--panel-bg);
}
.foot {
  border-top: var(--border-width) solid var(--border);
  padding: 8px 10px;
  background: var(--panel-bg);
}
@keyframes title-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}
</style>
