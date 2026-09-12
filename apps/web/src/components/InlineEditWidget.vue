<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { unifiedLines, type DiffLine } from '@/utils/inlineDiff'
import { t } from '@/i18n'

const props = defineProps<{
  instruction: string
  phase: 'prompt' | 'loading' | 'diff'
  original: string
  replacement: string
  error: string
  left: number
  top: number
  lineLabel: string
}>()

const emit = defineEmits<{
  'update:instruction': [value: string]
  submit: []
  accept: []
  reject: []
  close: []
}>()

const inputEl = ref<HTMLInputElement | null>(null)
const diffLines = computed<DiffLine[]>(() => unifiedLines(props.original, props.replacement))
const shownDiff = computed(() => {
  const lines = diffLines.value
  if (lines.length <= 16) return lines
  const changed = lines.map((row, i) => ({ row, i })).filter((x) => x.row.type !== 'eq')
  if (!changed.length) return lines.slice(0, 16)
  const start = Math.max(0, changed[0].i - 2)
  return lines.slice(start, start + 16)
})

watch(
  () => props.phase,
  async (phase) => {
    if (phase === 'prompt') {
      await nextTick()
      inputEl.value?.focus()
      inputEl.value?.select()
    }
  },
  { immediate: true },
)

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    emit('close')
    return
  }
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && props.phase === 'diff') {
    e.preventDefault()
    emit('accept')
    return
  }
  if (e.key === 'Enter' && !e.shiftKey && props.phase !== 'loading') {
    e.preventDefault()
    if (props.phase === 'diff') emit('accept')
    else emit('submit')
  }
}
</script>

<template>
  <div
    class="inline-edit"
    :style="{ left: `${left}px`, top: `${top}px` }"
    role="dialog"
    :aria-label="t('editor.inlineEdit')"
    @keydown="onKey"
    @mousedown.stop
  >
    <header class="ie-head">
      <AppIcon name="sparkles" :size="14" :stroke-width="1.75" />
      <span>{{ t('editor.inlineEdit') }}</span>
      <small>{{ lineLabel }}</small>
      <button type="button" class="ghost-icon-btn" :title="t('common.close')" @click="emit('close')">
        <AppIcon name="close" :size="12" :stroke-width="1.75" />
      </button>
    </header>
    <input
      ref="inputEl"
      class="ie-input"
      :value="instruction"
      :placeholder="t('editor.inlineEditPlaceholder')"
      :disabled="phase === 'loading'"
      @input="emit('update:instruction', ($event.target as HTMLInputElement).value)"
    />
    <p v-if="error" class="ie-error">{{ error }}</p>
    <div v-if="phase === 'diff'" class="ie-diff" aria-label="diff">
      <div v-for="(row, i) in shownDiff" :key="i" class="ie-line" :class="row.type">
        <span class="mark">{{ row.type === 'add' ? '+' : row.type === 'del' ? '-' : ' ' }}</span>
        <span class="txt">{{ row.text || ' ' }}</span>
      </div>
    </div>
    <footer class="ie-foot">
      <span class="hint">{{ phase === 'loading' ? t('editor.inlineEditGenerating') : t('editor.inlineEditHint') }}</span>
      <div class="ie-actions">
        <button v-if="phase === 'diff'" type="button" class="ghost-btn" @click="emit('reject')">
          {{ t('editor.inlineEditReject') }}
        </button>
        <button
          v-if="phase !== 'diff'"
          type="button"
          class="primary-btn"
          :disabled="phase === 'loading' || !instruction.trim()"
          @click="emit('submit')"
        >
          {{ t('editor.inlineEditGenerate') }}
        </button>
        <button v-else type="button" class="primary-btn" @click="emit('accept')">
          {{ t('editor.inlineEditAccept') }}
        </button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.inline-edit {
  position: absolute;
  z-index: 20;
  width: min(480px, calc(100% - 24px));
  border: var(--border-width) solid var(--border);
  border-radius: 10px;
  background: var(--panel-bg);
  box-shadow: 0 12px 32px color-mix(in srgb, #000 28%, transparent);
  overflow: hidden;
}
.ie-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px 6px;
  font-size: 12px;
  font-weight: 650;
  color: var(--text-h);
}
.ie-head small {
  flex: 1;
  min-width: 0;
  font-weight: 500;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ie-head .ghost-icon-btn {
  margin-left: auto;
}
.ie-input {
  display: block;
  width: calc(100% - 20px);
  margin: 0 10px 8px;
  height: 32px;
  padding: 0 10px;
  border: var(--border-width) solid var(--border);
  border-radius: 7px;
  background: var(--code-bg);
  color: var(--text-h);
  font-size: 13px;
}
.ie-error {
  margin: 0 12px 8px;
  font-size: 12px;
  color: #dc2626;
}
.ie-diff {
  max-height: 180px;
  overflow: auto;
  margin: 0 10px 8px;
  border: var(--border-width) solid var(--border);
  border-radius: 7px;
  font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--editor-bg);
}
.ie-line {
  display: flex;
  gap: 8px;
  padding: 0 8px;
  white-space: pre;
}
.ie-line.del {
  background: color-mix(in srgb, #dc2626 16%, transparent);
  color: color-mix(in srgb, #dc2626 70%, var(--text-h));
}
.ie-line.add {
  background: color-mix(in srgb, #16a34a 16%, transparent);
  color: color-mix(in srgb, #16a34a 70%, var(--text-h));
}
.ie-line .mark {
  width: 10px;
  flex-shrink: 0;
  opacity: 0.7;
}
.ie-line .txt {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ie-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px 8px;
}
.hint {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: var(--text-muted);
}
.ie-actions {
  display: flex;
  gap: 6px;
}
.ghost-btn,
.primary-btn {
  height: 26px;
  padding: 0 10px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}
.ghost-btn {
  border: var(--border-width) solid var(--border);
  background: transparent;
  color: var(--text-h);
}
.primary-btn {
  border: 0;
  background: var(--primary);
  color: #fff;
}
.primary-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
