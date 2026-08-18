<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'

const props = defineProps<{ block: Block }>()
const streaming = computed(() => props.block.status === 'streaming')
const bodyEl = ref<HTMLElement | null>(null)

watch(
  () => props.block.text,
  async () => {
    const el = bodyEl.value
    if (el) el.scrollTop = el.scrollHeight
  },
)
</script>

<template>
  <EventCard
    icon="think"
    title="思考过程"
    tone="think"
    :status="block.status"
    :default-open="false"
    :subtitle="streaming ? '正在思考…' : (block.text ? '已生成思考内容' : '')"
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
