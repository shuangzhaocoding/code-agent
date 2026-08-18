<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    summary: string
    details?: string
    confirmLabel?: string
    cancelLabel?: string
    danger?: boolean
  }>(),
  { confirmLabel: '确认', cancelLabel: '取消', danger: true, details: '' },
)

const emit = defineEmits<{ confirm: []; cancel: [] }>()
</script>

<template>
  <div class="mask" @mousedown.self="emit('cancel')">
    <section class="sheet" role="dialog" aria-modal="true">
      <h3>{{ title }}</h3>
      <p class="summary">{{ summary }}</p>
      <pre v-if="details" class="details">{{ details }}</pre>
      <footer>
        <button type="button" class="btn" @click="emit('cancel')">{{ cancelLabel }}</button>
        <button type="button" class="btn" :class="danger ? 'danger' : 'primary'" @click="emit('confirm')">
          {{ confirmLabel }}
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
  border-radius: 14px;
  background: var(--bg-elevated);
  box-shadow: var(--shadow-md);
  padding: 16px 16px 14px;
}
h3 {
  margin: 0 0 8px;
  font-size: 15px;
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
.btn {
  height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
}
.btn.primary {
  border-color: color-mix(in srgb, var(--primary) 45%, var(--border));
  background: var(--primary-soft);
  color: var(--primary);
}
.btn.danger {
  border-color: color-mix(in srgb, var(--danger) 40%, var(--border));
  background: color-mix(in srgb, var(--danger) 12%, var(--bg-elevated));
  color: var(--danger);
}
</style>
