<script setup lang="ts">
import { computed } from 'vue'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'
import { formatApprovalDetails } from '@/utils/approvals'

const props = defineProps<{ block: Block }>()

const summary = computed(() => String(props.block.meta.summary || '需要确认这次操作'))
const tool = computed(() => String(props.block.meta.tool || 'tool'))
const decision = computed(() => String(props.block.meta.decision || ''))
const pending = computed(() => !decision.value && props.block.status === 'streaming')
const details = computed(() => formatApprovalDetails(props.block.meta.details))
</script>

<template>
  <!--
    Work-process history card. Live actions live in ApprovalActionBar above the composer;
    streaming inline context uses ApprovalInlineHint under the tool call.
  -->
  <EventCard
    icon="alert"
    title="操作确认"
    :subtitle="tool"
    tone="danger"
    :status="pending ? 'streaming' : decision === 'denied' ? 'error' : 'ok'"
    :default-open="false"
  >
    <p class="summary">{{ summary }}</p>
    <pre v-if="details" class="details">{{ details }}</pre>
    <template v-if="decision" #footer>
      <p class="done">{{ decision === 'approved' ? '已允许' : '已拒绝' }}</p>
    </template>
  </EventCard>
</template>

<style scoped>
.summary {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
}
.details {
  margin: 8px 0 0;
  max-height: 180px;
  overflow: auto;
  font-family: var(--mono);
  font-size: 12px;
  color: var(--text-secondary);
  white-space: pre-wrap;
}
.done {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
