<script setup lang="ts">
import { computed } from 'vue'
import type { ContextUsageLevel } from '@/types/contextUsage'

const props = withDefaults(
  defineProps<{
    percent?: number
    level?: ContextUsageLevel
    loading?: boolean
    size?: number
    strokeWidth?: number
    disabled?: boolean
  }>(),
  {
    percent: 0,
    level: 'normal',
    loading: false,
    size: 20,
    strokeWidth: 1.5,
    disabled: false,
  },
)

const emit = defineEmits<{ click: [] }>()

const radius = computed(() => (props.size - props.strokeWidth) / 2 - 1)
const center = computed(() => props.size / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)

const strokeDashoffset = computed(() => {
  const clamped = Math.min(100, Math.max(0, props.percent))
  return circumference.value * (1 - clamped / 100)
})

const levelClass = computed(() => {
  if (props.level === 'warning') return 'is-warning'
  if (props.level === 'danger' || props.level === 'critical') return 'is-danger'
  return 'is-normal'
})

const tooltip = computed(() => `上下文用量 ${props.percent.toFixed(1)}%`)

function handleClick() {
  if (props.disabled) return
  emit('click')
}
</script>

<template>
  <button
    type="button"
    class="ghost-icon-btn chat-context-usage-button"
    :class="[levelClass, { 'is-loading': loading }]"
    :aria-label="tooltip"
    :title="tooltip"
    :disabled="disabled"
    @click="handleClick"
  >
    <svg
      class="chat-context-usage-button__svg"
      :width="size"
      :height="size"
      :viewBox="`0 0 ${size} ${size}`"
      aria-hidden="true"
    >
      <circle
        class="chat-context-usage-button__track"
        :cx="center"
        :cy="center"
        :r="radius"
        fill="none"
        :stroke-width="strokeWidth"
      />
      <circle
        class="chat-context-usage-button__progress"
        :class="levelClass"
        :cx="center"
        :cy="center"
        :r="radius"
        fill="none"
        :stroke-width="strokeWidth"
        stroke-linecap="round"
        :stroke-dasharray="`${circumference} ${circumference}`"
        :stroke-dashoffset="strokeDashoffset"
        :transform="`rotate(-90 ${center} ${center})`"
      />
    </svg>
  </button>
</template>

<style scoped>
.chat-context-usage-button__track {
  stroke: var(--border);
}

.chat-context-usage-button__progress {
  stroke: currentColor;
  transition: stroke-dashoffset 0.25s ease, stroke 0.2s ease;
}

.chat-context-usage-button.is-warning .chat-context-usage-button__progress {
  stroke: #e6a700;
}

.chat-context-usage-button.is-danger .chat-context-usage-button__progress {
  stroke: var(--danger);
}

.chat-context-usage-button.is-loading .chat-context-usage-button__progress {
  opacity: 0.55;
}

.chat-context-usage-button.is-loading {
  animation: chat-context-usage-pulse 1.2s ease-in-out infinite;
}

@keyframes chat-context-usage-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.65; }
}
</style>
