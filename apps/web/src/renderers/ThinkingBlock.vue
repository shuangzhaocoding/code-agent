<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'

const props = defineProps<{ block: Block }>()
const streaming = computed(() => props.block.status === 'streaming')
const bodyEl = ref<HTMLElement | null>(null)
const elapsed = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

function updateElapsed() {
  if (props.block.started_at) {
    const end = props.block.ended_at || Date.now()
    elapsed.value = Math.round((end - props.block.started_at) / 100) / 10
  }
}

onMounted(() => {
  updateElapsed()
  timer = setInterval(updateElapsed, 100)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

watch(() => props.block.status, () => {
  updateElapsed()
  if (!streaming.value && timer) {
    clearInterval(timer)
    timer = null
  }
})

watch(
  () => props.block.text,
  async () => {
    const el = bodyEl.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

const timeLabel = computed(() => {
  if (!props.block.started_at) return ''
  return `${elapsed.value.toFixed(1)}s`
})

const subtitle = computed(() => {
  if (streaming.value) return `正在思考… ${timeLabel.value}`
  if (props.block.text) return `已生成思考内容（${timeLabel.value}）`
  return ''
})
</script>

<template>
  <EventCard
    icon="think"
    title="思考过程"
    tone="think"
    :status="block.status"
    :default-open="false"
    :subtitle="subtitle"
  >
    <pre ref="bodyEl" class="think-body">{{ block.text || (streaming ? '正在思考…' : '（无内容）') }}<span v-if="streaming" class="caret" /></pre>
  </EventCard>
</template>

<style scoped>
.think-body {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
  font-size: 12.5px;
  font-family: var(--mono);
  line-height: 1.6;
  max-height: 360px;
  overflow: auto;
}
.caret {
  display: inline-block;
  width: 6px;
  height: 12px;
  margin-left: 2px;
  background: #8b5cf6;
  vertical-align: -1px;
  animation: blink 1s step-end infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
</style>
