<script setup lang="ts">
import { computed } from 'vue'
import type { Block } from '@/protocol/applyEvent'
import AppIcon from '@/components/AppIcon.vue'

const props = defineProps<{ block: Block }>()

const summary = computed(() => String(props.block.meta.summary || '需要确认这次操作'))
const decision = computed(() => String(props.block.meta.decision || ''))
const pending = computed(() => !decision.value && props.block.status === 'streaming')
</script>

<template>
  <div class="hint" :class="{ pending, done: !!decision }">
    <AppIcon class="icon" name="alert" :size="13" :stroke-width="1.75" />
    <span v-if="pending" class="text">等待确认：{{ summary }}</span>
    <span v-else class="text">{{ decision === 'approved' ? '已允许' : '已拒绝' }} · {{ summary }}</span>
    <span v-if="pending" class="cue">请在下方确认</span>
  </div>
</template>

<style scoped>
.hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 2px 0 6px 8px;
  padding: 6px 10px;
  border-left: 2px solid color-mix(in srgb, var(--danger) 55%, var(--border));
  border-radius: 0 8px 8px 0;
  background: color-mix(in srgb, var(--danger) 6%, transparent);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.35;
}
.hint.done {
  border-left-color: var(--border);
  background: color-mix(in srgb, var(--text-muted) 6%, transparent);
}
.icon {
  flex-shrink: 0;
  color: var(--danger);
}
.hint.done .icon {
  color: var(--text-muted);
}
.text {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cue {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 11px;
}
</style>
