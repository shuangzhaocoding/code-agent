<script setup lang="ts">
import { ref } from 'vue'
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
const open = ref(props.defaultOpen)

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
  <div class="card" :class="[tone, status, { open }]">
    <div class="row">
      <div class="head" :class="{ activatable }" @click="onHeadClick">
        <span class="glyph" aria-hidden="true">
          <AppIcon :name="icon" :size="14" />
        </span>
        <span class="titles">
          <span class="title" :class="{ running: status === 'streaming' }">{{ title }}</span>
          <span v-if="subtitle" class="sub">{{ subtitle }}</span>
        </span>
        <span v-if="status === 'error'" class="pill error">失败</span>
        <button type="button" class="chev-btn" @click="onChevron">
          <AppIcon class="chev" name="chevron" :size="14" />
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
  margin: 2px 0;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  overflow: clip;
  overflow-anchor: none;
  contain: layout style;
  box-shadow: var(--shadow);
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
  gap: 10px;
  min-height: 42px;
  padding: 8px 12px;
  border: 0;
  background: color-mix(in srgb, var(--bg-muted) 55%, var(--bg-elevated));
  color: var(--text);
  cursor: pointer;
  text-align: left;
  min-width: 0;
  width: 100%;
}
.card.error { border-color: color-mix(in srgb, var(--danger) 34%, var(--border)); }
.head:hover { background: var(--bg-muted); }
.head.activatable .titles { cursor: pointer; }
.head.activatable .sub { color: var(--primary); }
.glyph {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--bg-muted);
  color: var(--text-secondary);
}
.think .glyph {
  color: #7c3aed;
  background: color-mix(in srgb, #8b5cf6 16%, var(--bg-elevated));
}
.danger .glyph {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 16%, var(--bg-elevated));
}
.tool .glyph {
  color: var(--primary);
  background: var(--primary-soft);
}
.titles {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: row;
  align-items: baseline;
  gap: 8px;
  min-height: 20px;
}
.title {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.01em;
  white-space: nowrap;
}
.title.running {
  animation: title-pulse 1.2s ease-in-out infinite;
}
.sub {
  min-width: 0;
  flex: 1;
  font-size: 11.5px;
  color: var(--text-muted);
  font-family: var(--mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pill {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
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
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
}
.chev-btn:hover { background: var(--bg-elevated); color: var(--text); }
.chev { transition: transform 0.16s ease; transform: rotate(-90deg); }
.open .chev { transform: rotate(0deg); }
.body {
  flex: 1;
  min-width: 0;
  padding: 10px 12px 12px;
  background: var(--bg);
}
.foot {
  border-top: var(--border-width) solid var(--border);
  padding: 8px 12px 10px;
  background: var(--bg);
}
@keyframes title-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}
</style>
