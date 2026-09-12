<script setup lang="ts">
import AppIcon from '@/components/AppIcon.vue'
import { t } from '@/i18n'

defineProps<{
  kind: 'file' | 'dir'
  deleted?: boolean
  stagedOnly?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  action: [id: string]
}>()
</script>

<template>
  <span class="git-hover-actions" @click.stop @dblclick.stop @pointerdown.stop>
    <button
      v-if="kind === 'file'"
      type="button"
      class="act"
      :title="t('git.openFile')"
      :disabled="disabled || deleted"
      @click.stop="emit('action', 'open-file')"
    >
      <AppIcon name="file" :size="13" :stroke-width="1.75" />
    </button>
    <button
      type="button"
      class="act"
      :title="stagedOnly ? t('git.unstage') : t('git.stage')"
      :disabled="disabled"
      @click.stop="emit('action', stagedOnly ? 'unstage' : 'stage')"
    >
      <AppIcon :name="stagedOnly ? 'minus' : 'plus'" :size="13" :stroke-width="1.75" />
    </button>
    <button
      type="button"
      class="act danger"
      :title="t('git.discard')"
      :disabled="disabled"
      @click.stop="emit('action', 'discard')"
    >
      <AppIcon name="trash" :size="13" :stroke-width="1.75" />
    </button>
    <button
      type="button"
      class="act"
      :title="t('git.ignore')"
      :disabled="disabled"
      @click.stop="emit('action', 'ignore')"
    >
      <AppIcon name="close" :size="13" :stroke-width="1.75" />
    </button>
  </span>
</template>

<style scoped>
.git-hover-actions {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  display: inline-flex;
  align-items: center;
  gap: 0;
  padding: 0 4px 0 14px;
  background: var(--git-row-bg, var(--panel-bg));
  box-shadow: -12px 0 10px -4px var(--git-row-bg, var(--panel-bg));
  opacity: 0;
  pointer-events: none;
  z-index: 6;
}
.act {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.act :deep(svg) {
  pointer-events: none;
}
.act:hover:not(:disabled) {
  color: var(--text-h);
  background: color-mix(in srgb, var(--text-h) 8%, transparent);
}
.act.danger:hover:not(:disabled) {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 12%, transparent);
}
.act:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>

