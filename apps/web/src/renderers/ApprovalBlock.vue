<script setup lang="ts">
import { computed } from 'vue'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'
import { useAppStore } from '@/stores/app'

const props = defineProps<{ block: Block }>()
const store = useAppStore()

const approvalId = computed(() => String(props.block.meta.approval_id || ''))
const summary = computed(() => String(props.block.meta.summary || '需要确认这次操作'))
const tool = computed(() => String(props.block.meta.tool || 'tool'))
const decision = computed(() => String(props.block.meta.decision || ''))
const pending = computed(() => !decision.value && props.block.status === 'streaming')

const details = computed(() => {
  const raw = props.block.meta.details
  if (!raw) return ''
  if (typeof raw === 'string') return raw
  try {
    return JSON.stringify(raw, null, 2)
  } catch {
    return String(raw)
  }
})

function decide(allowed: boolean) {
  if (!approvalId.value) return
  store.decideApproval(approvalId.value, allowed)
}
</script>

<template>
  <EventCard
    icon="alert"
    title="需要确认"
    :subtitle="tool"
    tone="danger"
    :status="pending ? 'streaming' : decision === 'denied' ? 'error' : 'ok'"
    :default-open="pending"
  >
    <p class="summary">{{ summary }}</p>
    <pre v-if="details" class="details">{{ details }}</pre>
    <template v-if="pending || decision" #footer>
      <div v-if="pending" class="actions">
        <button type="button" class="btn ghost" @click.stop="decide(false)">拒绝</button>
        <button type="button" class="btn danger" @click.stop="decide(true)">允许执行</button>
      </div>
      <p v-else class="done">{{ decision === 'approved' ? '已允许' : '已拒绝' }}</p>
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
.actions { display: flex; justify-content: flex-end; gap: 8px; }
.btn {
  height: 26px;
  padding: 0 10px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
}
.btn.ghost {
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text-secondary);
}
.btn.danger {
  border: 1px solid color-mix(in srgb, var(--danger) 40%, var(--border));
  background: color-mix(in srgb, var(--danger) 12%, var(--bg-elevated));
  color: var(--danger);
}
.done {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
