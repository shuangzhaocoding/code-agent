<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'
import AppIcon from '@/components/AppIcon.vue'

const props = defineProps<{ block: Block }>()
const { t } = useI18n()

const command = computed(() => String(props.block.meta.command || ''))
const cwd = computed(() => {
  const value = props.block.meta.cwd
  return typeof value === 'string' ? value : undefined
})
const code = computed(() => props.block.meta.exit_code)
const isLaunch = computed(() => props.block.type === 'terminal.launch')
const title = computed(() => (isLaunch.value ? t('terminal.launchedTitle') : t('terminal.replayTitle')))

function openInTerminal() {
  if (!command.value) return
  window.dispatchEvent(
    new CustomEvent('ca-run-in-terminal', {
      detail: {
        command: command.value,
        cwd: cwd.value,
        newTab: true,
      },
    }),
  )
}
</script>

<template>
  <EventCard
    icon="terminal"
    :title="title"
    :subtitle="command"
    tone="default"
    :status="block.status"
    :default-open="isLaunch"
  >
    <pre class="term">{{ command ? `$ ${command}\n` : '' }}{{ block.text || (isLaunch ? t('terminal.launchedBody') : t('terminal.emptyOutput')) }}</pre>
    <div class="term-footer">
      <p v-if="code !== undefined && code !== null" class="code">{{ t('terminal.exitCode', { code }) }}</p>
      <button
        v-if="command"
        type="button"
        class="open-term-btn"
        @click="openInTerminal"
      >
        <AppIcon name="terminal" :size="14" :stroke-width="1.75" />
        {{ isLaunch ? t('terminal.reopenInTerminal') : t('terminal.openInTerminal') }}
      </button>
    </div>
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
.term-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.code {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}
.open-term-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  border: 1px solid var(--border);
  background: var(--bg-elevated, var(--bg));
  color: var(--text-secondary);
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}
.open-term-btn:hover {
  color: var(--text);
  border-color: var(--border-strong, var(--border));
}
</style>
