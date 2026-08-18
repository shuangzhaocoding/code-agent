<script setup lang="ts">
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'

defineProps<{ block: Block }>()
</script>

<template>
  <EventCard
    icon="alert"
    :title="String(block.meta.code || '错误')"
    tone="danger"
    status="error"
    :default-open="false"
  >
    <p class="err">{{ block.text || '发生错误' }}</p>
  </EventCard>
</template>

<style scoped>
.err {
  margin: 0;
  color: var(--danger);
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
}
</style>
