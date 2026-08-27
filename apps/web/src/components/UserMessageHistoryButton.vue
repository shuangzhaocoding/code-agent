<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'

defineProps<{
  active?: boolean
  disabled?: boolean
}>()

defineEmits<{
  toggle: []
}>()

const { t } = useI18n()
</script>

<template>
  <button
    type="button"
    class="history-trigger"
    :class="{ active }"
    :aria-pressed="active"
    :title="t('chat.userHistory')"
    :disabled="disabled"
    @click="$emit('toggle')"
  >
    <AppIcon name="history" :size="15" />
  </button>
</template>

<style scoped>
.history-trigger {
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}
.history-trigger:hover:not(:disabled) {
  background: var(--primary-soft);
  color: var(--primary);
}
.history-trigger.active {
  background: var(--primary-soft);
  color: var(--primary);
}
.history-trigger:disabled {
  opacity: 0.35;
  cursor: default;
}
</style>
