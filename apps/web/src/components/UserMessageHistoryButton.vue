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
    class="ghost-icon-btn"
    :class="{ active }"
    :aria-pressed="active"
    :title="t('chat.userHistory')"
    :disabled="disabled"
    @click="$emit('toggle')"
  >
    <AppIcon name="history" :size="16" :stroke-width="1.75" />
  </button>
</template>

<style scoped>
</style>
