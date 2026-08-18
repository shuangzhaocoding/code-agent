<script setup lang="ts">
import { computed } from 'vue'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'

const props = defineProps<{ block: Block }>()
const body = computed(() => {
  const parts = [props.block.text, JSON.stringify(props.block.meta, null, 2)].filter(Boolean)
  return parts.join('\n')
})
</script>

<template>
  <EventCard
    icon="wrench"
    :title="block.type"
    tone="default"
    :status="block.status"
    :default-open="false"
  >
    <pre class="raw">{{ body }}</pre>
  </EventCard>
</template>

<style scoped>
.raw {
  margin: 0;
  font-family: var(--mono);
  font-size: 11px;
  white-space: pre-wrap;
  color: var(--text-secondary);
  max-height: 240px;
  overflow: auto;
}
</style>
