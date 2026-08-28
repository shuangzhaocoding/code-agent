<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    title: string
    summary: string
    details?: string
    confirmLabel?: string
    cancelLabel?: string
    danger?: boolean
  }>(),
  { confirmLabel: '', cancelLabel: '', danger: true, details: '' },
)

const { t } = useI18n()
const emit = defineEmits<{ confirm: []; cancel: [] }>()
const confirmText = computed(() => props.confirmLabel || t('common.confirm'))
const cancelText = computed(() => props.cancelLabel || t('common.cancel'))
</script>

<template>
  <div class="mask" @mousedown.self="emit('cancel')">
    <section class="sheet" role="dialog" aria-modal="true">
      <h3>{{ title }}</h3>
      <p class="summary">{{ summary }}</p>
      <pre v-if="details" class="details">{{ details }}</pre>
      <footer>
        <button type="button" class="btn btn-ghost" @click="emit('cancel')">{{ cancelText }}</button>
        <button type="button" class="btn" :class="danger ? 'confirm-danger' : 'btn-primary'" @click="emit('confirm')">
          {{ confirmText }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 120;
  display: grid;
  place-items: center;
  padding: 24px;
  background: color-mix(in srgb, #000 42%, transparent);
}
.sheet {
  width: min(460px, 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: var(--shadow);
  padding: 16px 20px 14px;
}
h3 {
  margin: 0 0 8px;
  font-size: 16px;
  color: var(--text-h);
}
.summary {
  margin: 0;
  color: var(--text);
  font-size: 13.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
.details {
  margin: 10px 0 0;
  max-height: 180px;
  overflow: auto;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-family: var(--mono);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
.confirm-danger {
  background: var(--danger);
  color: #fff;
  font-weight: 600;
}
.confirm-danger:hover {
  opacity: 0.88;
}
</style>
