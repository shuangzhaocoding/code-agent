<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'

const props = defineProps<{ block: Block }>()
const { t } = useI18n()

const goal = computed(() => String(props.block.meta?.goal || ''))
const title = computed(() =>
  goal.value ? t('chat.exploreTitle', { goal: goal.value }) : t('chat.exploreFallback'),
)
</script>

<template>
  <EventCard
    icon="search"
    :title="title"
    :subtitle="goal"
    tone="think"
    :status="block.status"
    :default-open="block.status === 'streaming'"
  >
    <pre class="report">{{ block.text || t('chat.exploreRunning') }}</pre>
  </EventCard>
</template>

<style scoped>
.report {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  color: var(--text-secondary);
  max-height: 320px;
  overflow: auto;
}
</style>
