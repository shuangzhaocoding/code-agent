<script setup lang="ts">
import { computed } from 'vue'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'

const props = defineProps<{ block: Block }>()
const command = computed(() => String(props.block.meta.command || ''))
const code = computed(() => props.block.meta.exit_code)
</script>

<template>
  <EventCard
    icon="terminal"
    title="运行命令"
    :subtitle="command"
    tone="default"
    :status="block.status"
    :default-open="false"
  >
    <pre class="term">{{ command ? `$ ${command}\n` : '' }}{{ block.text || '（无输出）' }}</pre>
    <p v-if="code !== undefined && code !== null" class="code">退出码 {{ code }}</p>
  </EventCard>
</template>

<style scoped>
.term {
  margin: 0;
  background: var(--bg-muted);
  color: var(--text-secondary);
  border-radius: 8px;
  font-family: var(--mono);
  font-size: 12px;
  padding: 10px;
  white-space: pre-wrap;
  max-height: 240px;
  overflow: auto;
}
.code {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
