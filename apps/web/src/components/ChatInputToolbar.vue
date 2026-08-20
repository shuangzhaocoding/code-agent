<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'
import ToolbarSelect, { type ToolbarSelectOption } from '@/components/ToolbarSelect.vue'
import { THINKING_LEVELS, type ThinkingLevel } from '@/types/thinking'

const store = useAppStore()

const modeOptions: ToolbarSelectOption[] = [
  {
    value: 'ask',
    label: 'Ask',
    description: '快速问答，不调用工具',
    icon: 'chat',
    accent: '#0891b2',
  },
  {
    value: 'agent',
    label: 'Agent',
    description: '自主调用工具完成任务',
    icon: 'sparkles',
    accent: 'var(--primary)',
  },
  {
    value: 'plan',
    label: 'Plan',
    description: '先规划步骤，再逐步执行',
    icon: 'rocket',
    accent: '#d97706',
  },
]

const modelOptions = computed(() => {
  const options: ToolbarSelectOption[] = []
  for (const provider of store.providers) {
    for (const model of provider.models || []) {
      options.push({
        value: model.id,
        label: model.display_name,
        description: provider.name,
        icon: 'chip',
        group: provider.name,
      })
    }
  }
  return options
})

const thinkingOptions = computed(() =>
  THINKING_LEVELS.map((item) => ({
    value: item.value,
    label: item.label,
    description: item.description,
    icon: item.value === 'off' ? 'think' : 'sparkles',
    accent: item.value === 'off' ? undefined : '#7c3aed',
  })),
)

function onThinkingChange(value: string | null) {
  if (!value) return
  store.thinkingLevel = value as ThinkingLevel
}
</script>

<template>
  <div class="chat-input-toolbar">
    <ToolbarSelect
      :model-value="store.thinkingLevel"
      :options="thinkingOptions"
      :min-width="96"
      @update:model-value="onThinkingChange"
    />

    <ToolbarSelect
      :model-value="store.mode"
      :options="modeOptions"
      :min-width="108"
      @update:model-value="store.mode = $event as typeof store.mode"
    />

    <ToolbarSelect
      :model-value="store.modelId"
      :options="modelOptions"
      placeholder="选择模型"
      :min-width="128"
      grow
      @update:model-value="store.modelId = $event"
    />
  </div>
</template>

<style scoped>
.chat-input-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}
</style>
