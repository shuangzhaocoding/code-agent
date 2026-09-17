<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    title: string
    summary?: string
    label?: string
    defaultValue?: string
    placeholder?: string
    confirmLabel?: string
    cancelLabel?: string
    danger?: boolean
  }>(),
  {
    summary: '',
    label: '',
    defaultValue: '',
    placeholder: '',
    confirmLabel: '',
    cancelLabel: '',
    danger: false,
  },
)

const { t } = useI18n()
const emit = defineEmits<{ confirm: [value: string]; cancel: [] }>()
const value = ref(props.defaultValue)
const inputEl = ref<HTMLInputElement | null>(null)

const confirmText = computed(() => props.confirmLabel || t('common.confirm'))
const cancelText = computed(() => props.cancelLabel || t('common.cancel'))
const canSubmit = computed(() => Boolean(value.value.trim()))

function submit() {
  const next = value.value.trim()
  if (!next) return
  emit('confirm', next)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    emit('cancel')
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  await nextTick()
  const el = inputEl.value
  if (!el) return
  el.focus()
  el.select()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div class="mask" @mousedown.self="emit('cancel')">
    <section class="sheet" role="dialog" aria-modal="true" @keydown.enter.prevent="submit">
      <h3>{{ title }}</h3>
      <p v-if="summary" class="summary">{{ summary }}</p>
      <label class="field">
        <span v-if="label" class="field-label">{{ label }}</span>
        <input
          ref="inputEl"
          v-model="value"
          class="field-input"
          type="text"
          maxlength="120"
          :placeholder="placeholder"
          autocomplete="off"
          spellcheck="false"
        />
      </label>
      <footer>
        <button type="button" class="btn btn-ghost" @click="emit('cancel')">{{ cancelText }}</button>
        <button
          type="button"
          class="btn"
          :class="danger ? 'confirm-danger' : 'btn-primary'"
          :disabled="!canSubmit"
          @click="submit"
        >
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
  width: min(420px, 100%);
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
  margin: 0 0 12px;
  color: var(--text);
  font-size: 13.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.field-input {
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--text-h);
  font: inherit;
  font-size: 13px;
  outline: none;
}
.field-input:focus {
  border-color: color-mix(in srgb, var(--primary) 55%, var(--border));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 18%, transparent);
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
.btn:disabled {
  opacity: 0.45;
  cursor: default;
}
</style>
