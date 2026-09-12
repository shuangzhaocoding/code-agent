<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import AppIcon from '@/components/AppIcon.vue'
import type { PlanStep } from '@/utils/parsePlan'
import { useAppStore } from '@/stores/app'
import { useToast } from '@/composables/useToast'
import { fileLinkFromClickTarget, linkifyFilePathsInHtml } from '@/utils/chatFileLinks'

const props = defineProps<{
  steps: PlanStep[]
}>()

const { t } = useI18n()
const store = useAppStore()
const toast = useToast()
const open = ref<Set<number>>(new Set())
const checked = ref<Set<number>>(new Set())
const executing = ref(false)
/** After confirm execute succeeds, freeze selection so the plan can't be re-submitted. */
const locked = ref(false)
const purifyOpts = { ADD_ATTR: ['target', 'rel', 'data-path', 'data-line', 'data-ca-file'] }

watch(
  () => props.steps.map((s) => s.index).join(','),
  () => {
    open.value = new Set()
    checked.value = new Set(props.steps.map((s) => s.index))
    locked.value = false
  },
  { immediate: true },
)

const selectedCount = computed(() => checked.value.size)
const allChecked = computed(
  () => props.steps.length > 0 && props.steps.every((s) => checked.value.has(s.index)),
)
const someChecked = computed(() => selectedCount.value > 0 && !allChecked.value)

function isOpen(index: number) {
  return open.value.has(index)
}

function isChecked(index: number) {
  return checked.value.has(index)
}

function toggleOpen(index: number) {
  const next = new Set(open.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  open.value = next
}

function toggleCheck(index: number) {
  if (locked.value) return
  const next = new Set(checked.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  checked.value = next
}

function toggleAll() {
  if (locked.value) return
  if (allChecked.value) checked.value = new Set()
  else checked.value = new Set(props.steps.map((s) => s.index))
}

function detailHtml(detail: string) {
  if (!detail.trim()) return ''
  const root = store.workspace?.root_path || ''
  const linked = linkifyFilePathsInHtml(marked.parse(detail, { breaks: true }) as string, root)
  return DOMPurify.sanitize(linked, purifyOpts)
}

function onDetailClick(e: MouseEvent) {
  const fileLink = fileLinkFromClickTarget(e.target)
  if (!fileLink) return
  e.preventDefault()
  e.stopPropagation()
  void store.openChatFilePath(fileLink.path, fileLink.line)
}

function buildExecutePrompt(selected: PlanStep[]) {
  const lines = selected.map((step) => {
    const head = `${step.index}. ${step.title}`
    return step.detail ? `${head}\n   ${step.detail}` : head
  })
  return `${t('plan.executeLead')}\n\n${lines.join('\n')}`
}

async function confirmExecute() {
  if (locked.value || executing.value || store.isRunBusy()) return
  if (!store.hasConfiguredModel) {
    toast.warning(t('chat.needModel'))
    window.dispatchEvent(new Event('ca-open-models'))
    return
  }
  const selected = props.steps.filter((s) => checked.value.has(s.index))
  if (!selected.length) {
    toast.warning(t('plan.selectAtLeastOne'))
    return
  }
  executing.value = true
  try {
    store.mode = 'agent'
    await store.sendNow(buildExecutePrompt(selected))
    locked.value = true
    window.dispatchEvent(new Event('ca-focus-composer'))
  } catch (err) {
    toast.error(err instanceof Error ? err.message : t('chat.sendFailed'))
  } finally {
    executing.value = false
  }
}
</script>

<template>
  <div class="plan-board" :class="{ locked }">
    <div class="plan-head">
      <button
        type="button"
        class="plan-box"
        :class="{ on: allChecked, partial: someChecked }"
        :aria-checked="allChecked ? 'true' : someChecked ? 'mixed' : 'false'"
        :aria-label="allChecked ? t('plan.deselectAll') : t('plan.selectAll')"
        :disabled="locked"
        role="checkbox"
        @click="toggleAll"
      >
        <span class="plan-box-mark" aria-hidden="true" />
      </button>
      <span class="plan-kicker">{{ t('plan.title') }}</span>
      <span class="plan-count">{{ t('plan.count', { n: steps.length }) }}</span>
      <span v-if="locked" class="plan-locked-badge">{{ t('plan.executed') }}</span>
    </div>
    <ol class="plan-list">
      <li
        v-for="step in steps"
        :key="step.index"
        class="plan-item"
        :class="{ open: isOpen(step.index), 'has-detail': !!step.detail, checked: isChecked(step.index) }"
      >
        <div class="plan-row">
          <button
            type="button"
            class="plan-box"
            :class="{ on: isChecked(step.index) }"
            :aria-checked="isChecked(step.index)"
            :aria-label="step.title"
            :disabled="locked"
            role="checkbox"
            @click.stop="toggleCheck(step.index)"
          >
            <span class="plan-box-mark" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="plan-main"
            :aria-expanded="isOpen(step.index)"
            :disabled="!step.detail"
            @click="step.detail && toggleOpen(step.index)"
          >
            <span class="plan-index">{{ step.index }}</span>
            <span class="plan-title">{{ step.title }}</span>
            <AppIcon v-if="step.detail" class="plan-chev" name="chevron-right" :size="13" />
          </button>
        </div>
        <div v-if="step.detail && isOpen(step.index)" class="plan-body" @click="onDetailClick">
          <div class="markdown-body" v-html="detailHtml(step.detail)" />
        </div>
      </li>
    </ol>
    <div class="plan-foot">
      <button
        type="button"
        class="btn btn-primary plan-execute"
        :disabled="locked || executing || store.isRunBusy() || selectedCount === 0"
        @click="confirmExecute"
      >
        {{
          locked
            ? t('plan.executed')
            : executing
              ? t('plan.executing')
              : t('plan.confirmExecute', { n: selectedCount })
        }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.plan-board {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 2px 0 6px;
  position: relative;
  z-index: 0;
}
.plan-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 20px;
  padding: 0 2px;
  position: relative;
  z-index: 0;
}
.plan-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--primary);
  line-height: 1;
}
.plan-count {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1;
}
.plan-locked-badge {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
}
/* In-flow checkbox mark — avoid absolute ::after, which can paint against .agent in web Chromium */
.plan-box {
  box-sizing: border-box;
  width: 14px;
  height: 14px;
  margin: 0;
  padding: 0;
  flex-shrink: 0;
  align-self: center;
  border: 1.5px solid color-mix(in srgb, var(--text-muted) 55%, var(--border));
  border-radius: 3px;
  background: var(--panel-bg);
  color: inherit;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: relative;
  top: auto;
  left: auto;
  right: auto;
  bottom: auto;
  inset: auto;
  isolation: isolate;
  overflow: hidden;
  transform: translateZ(0);
}
.plan-box:disabled {
  cursor: default;
  opacity: 0.72;
}
.plan-box.on,
.plan-box.partial {
  border-color: var(--primary);
}
.plan-box.on {
  background: var(--primary);
}
.plan-box.partial {
  background: color-mix(in srgb, var(--primary) 12%, var(--panel-bg));
}
.plan-box-mark {
  display: none;
  flex-shrink: 0;
  pointer-events: none;
}
.plan-box.on .plan-box-mark {
  display: block;
  width: 4px;
  height: 7px;
  margin-top: -1px;
  border: solid #fff;
  border-width: 0 1.5px 1.5px 0;
  transform: rotate(45deg);
}
.plan-box.partial .plan-box-mark {
  display: block;
  width: 8px;
  height: 1.5px;
  border: 0;
  border-radius: 1px;
  background: var(--primary);
  transform: none;
}
.plan-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: var(--border-width) solid var(--border);
  border-radius: 12px;
  background: var(--panel-bg);
}
.plan-item:first-child {
  border-top-left-radius: 11px;
  border-top-right-radius: 11px;
}
.plan-item:last-child {
  border-bottom-left-radius: 11px;
  border-bottom-right-radius: 11px;
}
.plan-item + .plan-item {
  border-top: var(--border-width) solid var(--border);
}
.plan-row {
  display: flex;
  align-items: center;
  gap: 0;
  min-height: 44px;
}
.plan-row > .plan-box {
  margin-left: 12px;
  margin-right: 8px;
}
.plan-main {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 11px 12px 11px 4px;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.plan-item:first-child .plan-main {
  border-top-right-radius: 11px;
}
.plan-item:last-child .plan-main {
  border-bottom-right-radius: 11px;
}
.plan-item.has-detail .plan-main:hover {
  background: color-mix(in srgb, var(--primary) 7%, var(--code-bg));
}
.plan-item:not(.has-detail) .plan-main {
  cursor: default;
}
.plan-item.checked .plan-index {
  color: #fff;
  background: var(--primary);
}
.plan-index {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 14%, var(--code-bg));
}
.plan-item.open .plan-index {
  color: #fff;
  background: var(--primary);
}
.plan-title {
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-h);
}
.plan-chev {
  color: var(--text-muted);
  opacity: 0.8;
  transition: transform 0.15s ease;
}
.plan-item.open .plan-chev {
  transform: rotate(90deg);
}
.plan-body {
  padding: 0 14px 12px 44px;
  color: var(--text-secondary);
  font-size: 12.5px;
  line-height: 1.6;
}
.plan-body :deep(.markdown-body) {
  color: inherit;
  font-size: inherit;
}
.plan-body :deep(.markdown-body p:first-child) { margin-top: 0; }
.plan-body :deep(.markdown-body p:last-child) { margin-bottom: 0; }
.plan-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 0 2px;
}
.plan-execute {
  margin-left: auto;
}
.plan-board.locked .plan-execute {
  opacity: 0.7;
}
</style>
