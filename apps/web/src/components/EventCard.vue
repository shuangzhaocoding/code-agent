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
  if (props.activatable) emit('activate')
  else toggle()
}

function onChevron(e: Event) {
  e.preventDefault()
  e.stopPropagation()
  toggle()
}
</script>

<template>
  <div class="card" :class="[tone, status, { open }]">
    <div class="head" :class="{ activatable }" @click="onHeadClick">
      <span class="glyph" aria-hidden="true">
        <AppIcon :name="icon" :size="14" />
      </span>
      <span class="titles">
        <span class="title">{{ title }}</span>
        <span v-if="subtitle" class="sub">{{ subtitle }}</span>
      </span>
      <span class="dots" :class="{ on: status === 'streaming' }" aria-hidden="true"><i /><i /><i /></span>
      <span v-if="status === 'error'" class="pill error">失败</span>
      <button type="button" class="chev-btn" @click="onChevron">
        <AppIcon class="chev" name="chevron" :size="14" />
      </button>
    </div>
    <div v-show="open" class="body">
      <slot />
    </div>
    <div v-if="$slots.footer" class="foot">
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.card {
  margin: 8px 0;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-elevated);
  overflow: clip;
  overflow-anchor: none;
  contain: layout style;
  box-shadow: var(--shadow);
}
.card.think { border-color: color-mix(in srgb, #8b5cf6 32%, var(--border)); }
.card.danger { border-color: color-mix(in srgb, var(--danger) 34%, var(--border)); }
.card.tool { border-color: color-mix(in srgb, var(--primary) 26%, var(--border)); }
.head {
  width: 100%;
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
}
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
  flex-direction: column;
  justify-content: center;
  gap: 1px;
  min-height: 32px;
}
.title {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.01em;
}
.sub {
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
}
.pill.error {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 12%, var(--bg-elevated));
}
.dots {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 22px;
  height: 12px;
  flex-shrink: 0;
  color: var(--primary);
  opacity: 0;
  pointer-events: none;
}
.dots.on { opacity: 1; }
.dots i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.25;
}
.dots.on i { animation: typing 1.05s ease-in-out infinite; }
.dots.on i:nth-child(2) { animation-delay: 0.15s; }
.dots.on i:nth-child(3) { animation-delay: 0.3s; }
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
.chev { transition: transform 0.16s ease; }
.open .chev { transform: rotate(180deg); }
.body {
  border-top: 1px solid var(--border);
  padding: 10px 12px 12px;
  background: var(--bg);
}
.foot {
  border-top: 1px solid var(--border);
  padding: 8px 12px 10px;
  background: var(--bg);
}
@keyframes typing {
  0%, 80%, 100% { opacity: 0.25; }
  40% { opacity: 1; }
}
</style>
