<script setup lang="ts">
import { computed, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import ToolbarSelect, { type ToolbarSelectOption } from '@/components/ToolbarSelect.vue'
import AppIcon from '@/components/AppIcon.vue'
import { THINKING_LEVELS, type ThinkingLevel } from '@/types/thinking'
import type { LlmModel } from '@/types/llm'

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

function isProbed(model: LlmModel) {
  return model.availability != null && model.availability.ok != null
}

function isAvailable(model: LlmModel) {
  return model.availability?.ok === true
}

const allModels = computed(() =>
  store.providers.flatMap((provider) =>
    (provider.models || []).map((model) => ({ provider, model })),
  ),
)

const visibleModels = computed(() => {
  const rows = allModels.value
  const probed = rows.some(({ model }) => isProbed(model))
  if (!probed) return rows
  return rows.filter(({ model }) => isAvailable(model) || model.id === store.modelId)
})

const modelOptions = computed(() =>
  visibleModels.value.map(({ provider, model }) => {
    const probed = isProbed(model)
    const ok = isAvailable(model)
    return {
      value: model.id,
      label: model.display_name,
      description: provider.name,
      icon: 'chip',
      group: provider.name,
      badge: !probed ? '未检测' : ok ? '可用' : '不可用',
      badgeKind: !probed ? 'unknown' : ok ? 'ok' : 'fail',
    } satisfies ToolbarSelectOption
  }),
)

const thinkingOptions = computed(() =>
  THINKING_LEVELS.map((item) => ({
    value: item.value,
    label: item.label,
    description: item.description,
    icon: item.value === 'off' ? 'think' : 'sparkles',
    accent: item.value === 'off' ? undefined : '#7c3aed',
  })),
)

watch(
  visibleModels,
  (rows) => {
    if (!rows.length) return
    if (rows.some(({ model }) => model.id === store.modelId)) return
    const available = rows.find(({ model }) => isAvailable(model)) || rows[0]
    if (available) store.modelId = available.model.id
  },
  { immediate: true },
)

function onThinkingChange(value: string | null) {
  if (!value) return
  store.thinkingLevel = value as ThinkingLevel
}

function openModelsAndProbe() {
  store.pendingModelProbe = true
  window.dispatchEvent(new CustomEvent('ca-open-models'))
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
      placeholder="选择可用模型"
      :min-width="128"
      grow
      @update:model-value="store.modelId = $event"
    />
    <button
      type="button"
      class="probe-btn"
      :disabled="!store.providers.length"
      title="打开模型页并检测可用性"
      @click="openModelsAndProbe"
    >
      <AppIcon name="refresh" :size="14" />
    </button>
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
.probe-btn {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border: 0;
  border-radius: 999px;
  background: var(--panel-bg);
  color: var(--text-secondary);
  display: grid;
  place-items: center;
  cursor: pointer;
}
.probe-btn:hover:not(:disabled) {
  background: var(--code-bg);
  color: var(--primary);
}
.probe-btn:disabled {
  cursor: default;
  opacity: 0.7;
}
</style>
