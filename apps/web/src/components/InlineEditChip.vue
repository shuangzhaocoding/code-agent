<script setup lang="ts">
import AppIcon from '@/components/AppIcon.vue'
import { isMacMod } from '@/utils/relativeTime'
import { t } from '@/i18n'

defineProps<{
  left: number
  top: number
}>()

const emit = defineEmits<{
  open: []
}>()

const shortcut = isMacMod() ? '⌘K' : 'Ctrl+K'
</script>

<template>
  <button
    type="button"
    class="ie-chip"
    :style="{ left: `${left}px`, top: `${top}px` }"
    :title="t('editor.inlineEdit')"
    @mousedown.prevent.stop
    @click.stop="emit('open')"
  >
    <AppIcon name="sparkles" :size="13" :stroke-width="1.75" />
    <span>{{ t('editor.inlineEdit') }}</span>
    <kbd>{{ shortcut }}</kbd>
  </button>
</template>

<style scoped>
.ie-chip {
  position: absolute;
  z-index: 19;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 8px 0 9px;
  border: var(--border-width) solid var(--border);
  border-radius: 8px;
  background: var(--panel-bg);
  color: var(--text-h);
  box-shadow: 0 8px 22px color-mix(in srgb, #000 22%, transparent);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.ie-chip:hover {
  border-color: color-mix(in srgb, var(--primary) 45%, var(--border));
  color: var(--primary);
}
kbd {
  padding: 1px 5px;
  border-radius: 4px;
  border: var(--border-width) solid var(--border);
  background: var(--code-bg);
  color: var(--text-muted);
  font: 600 10px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
</style>
