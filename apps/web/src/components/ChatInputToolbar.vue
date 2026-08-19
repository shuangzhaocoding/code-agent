<script setup lang="ts">
import { computed } from 'vue'
import { IconAtom } from '@opentiny/tiny-robot-svgs'
import { useAppStore } from '@/stores/app'

const store = useAppStore()

const models = computed(() =>
  store.providers.flatMap((p) =>
    (p.models || []).map((m: { id: string; display_name: string }) => ({
      ...m,
      provider: p.name as string,
    })),
  ),
)

function toggleThinking() {
  store.thinking = !store.thinking
}
</script>

<template>
  <div class="chat-input-toolbar">
    <button
      type="button"
      class="chat-input-toolbar__think"
      :class="{ 'is-active': store.thinking }"
      :title="store.thinking ? '深度思考：开' : '深度思考：关'"
      @click="toggleThinking"
    >
      <IconAtom class="chat-input-toolbar__icon" />
      <span>深度思考</span>
    </button>

    <label class="chat-input-toolbar__field">
      <span class="sr-only">模式</span>
      <select v-model="store.mode" class="chat-input-toolbar__select">
        <option value="ask">Ask</option>
        <option value="agent">Agent</option>
        <option value="plan">Plan</option>
      </select>
    </label>

    <label class="chat-input-toolbar__field chat-input-toolbar__field--grow">
      <span class="sr-only">模型</span>
      <select v-model="store.modelId" class="chat-input-toolbar__select">
        <option :value="null">选择模型</option>
        <option v-for="m in models" :key="m.id" :value="m.id">
          {{ m.display_name }}
        </option>
      </select>
    </label>
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

.chat-input-toolbar__think {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 14px;
  border: var(--border-width) solid transparent;
  border-radius: 999px;
  background: var(--panel-bg);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
  transition:
    background-color 0.2s,
    border-color 0.2s,
    color 0.2s;
  flex-shrink: 0;
}

.chat-input-toolbar__think:hover {
  background: var(--code-bg);
}

.chat-input-toolbar__think.is-active {
  color: var(--think-active-text);
  background: var(--think-active-bg);
  border-color: var(--think-active-border);
}

.chat-input-toolbar__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.chat-input-toolbar__field {
  display: inline-flex;
  min-width: 0;
  flex-shrink: 0;
}

.chat-input-toolbar__field--grow {
  flex: 1 1 120px;
  max-width: 220px;
}

.chat-input-toolbar__select {
  width: 100%;
  height: 32px;
  max-width: 100%;
  padding: 0 28px 0 12px;
  border: var(--border-width) solid transparent;
  border-radius: 999px;
  background-color: var(--panel-bg);
  background-image: var(--select-chevron);
  background-repeat: no-repeat;
  background-position: right 10px center;
  color: var(--text);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  appearance: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition:
    background-color 0.2s,
    border-color 0.2s,
    color 0.2s;
}

.chat-input-toolbar__select:hover {
  background-color: var(--code-bg);
}

.chat-input-toolbar__select:focus {
  outline: none;
  border-color: var(--primary);
  color: var(--text-h);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
