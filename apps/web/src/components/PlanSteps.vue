<script setup lang="ts">
import { ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import AppIcon from '@/components/AppIcon.vue'
import type { PlanStep } from '@/utils/parsePlan'

const props = defineProps<{
  steps: PlanStep[]
}>()

const open = ref<Set<number>>(new Set())

watch(
  () => props.steps.map((s) => s.index).join(','),
  () => {
    open.value = new Set()
  },
)

function isOpen(index: number) {
  return open.value.has(index)
}

function toggle(index: number) {
  const next = new Set(open.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  open.value = next
}

function detailHtml(detail: string) {
  if (!detail.trim()) return ''
  return DOMPurify.sanitize(marked.parse(detail, { breaks: true }) as string)
}

</script>

<template>
  <div class="plan-board">
    <header class="plan-head">
      <span class="plan-kicker">任务列表</span>
      <span class="plan-count">{{ steps.length }} 项</span>
    </header>
    <ol class="plan-list">
      <li
        v-for="step in steps"
        :key="step.index"
        class="plan-item"
        :class="{ open: isOpen(step.index), 'has-detail': !!step.detail }"
      >
        <button
          type="button"
          class="plan-row"
          :aria-expanded="isOpen(step.index)"
          :disabled="!step.detail"
          @click="step.detail && toggle(step.index)"
        >
          <span class="plan-index">{{ step.index }}</span>
          <span class="plan-title">{{ step.title }}</span>
          <AppIcon v-if="step.detail" class="plan-chev" name="chevron-right" :size="13" />
        </button>
        <div v-if="step.detail && isOpen(step.index)" class="plan-body">
          <div class="markdown-body" v-html="detailHtml(step.detail)" />
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.plan-board {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 2px 0 6px;
}
.plan-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 0 2px;
}
.plan-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--primary);
}
.plan-count {
  font-size: 11px;
  color: var(--text-muted);
}
.plan-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: var(--border-width) solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--panel-bg);
}
.plan-item + .plan-item {
  border-top: var(--border-width) solid var(--border);
}
.plan-row {
  width: 100%;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.plan-item.has-detail .plan-row:hover {
  background: color-mix(in srgb, var(--primary) 7%, var(--code-bg));
}
.plan-item:not(.has-detail) .plan-row {
  cursor: default;
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
</style>
