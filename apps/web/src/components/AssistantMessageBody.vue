<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { rendererFor } from '@/renderers'
import type { Block, ChatMessage } from '@/protocol/applyEvent'
import { matchApprovalHint } from '@/utils/approvals'
import { classifyBlock, isAnswerMarkdown, isConversationBlock } from '@/utils/trajectory'
import AppIcon from '@/components/AppIcon.vue'
import ApprovalInlineHint from '@/components/ApprovalInlineHint.vue'

const props = defineProps<{
  msg: ChatMessage
  /** True while this message's run is still streaming. */
  streaming?: boolean
}>()

const emit = defineEmits<{ toggle: [] }>()

const workExpanded = ref(false)

const finished = computed(() => !props.streaming)

const workBlocks = computed(() =>
  props.msg.blocks.filter((b) => {
    if (b.type === 'error') return false
    // Approvals belong in work process after the run (and never in the final answer).
    if (b.type === 'approval') return finished.value
    return !isConversationBlock(b.type)
  }),
)

const answerBlocks = computed(() => {
  const candidates = props.msg.blocks.filter(
    (b) => (b.type === 'assistant.markdown' && isAnswerMarkdown(b as Block)) || b.type === 'error',
  )
  if (!finished.value) {
    return props.msg.blocks.filter(
      (b) => b.type !== 'approval' && (isConversationBlock(b.type) || b.type === 'error'),
    )
  }
  if (candidates.length <= 1) {
    return props.msg.blocks.filter(
      (b) => b.type !== 'approval' && (isConversationBlock(b.type) || b.type === 'error'),
    )
  }
  const lastMd = candidates[candidates.length - 1]
  return props.msg.blocks.filter(
    (b) =>
      b.type === 'error' ||
      b.type === 'user.text' ||
      (b.type === 'assistant.markdown' && b === lastMd),
  )
})

const collapsedMarkdown = computed(() => {
  if (!finished.value) return [] as Block[]
  const answers = new Set(answerBlocks.value.map((b) => b.id))
  return props.msg.blocks.filter(
    (b) => b.type === 'assistant.markdown' && !answers.has(b.id),
  )
})

const hiddenWorkCount = computed(() => workBlocks.value.length + collapsedMarkdown.value.length)

const showCollapseChrome = computed(() => finished.value && hiddenWorkCount.value > 0)

type VisibleRow = {
  key: string
  block: Block
  hint?: Block
}

const visibleRows = computed((): VisibleRow[] => {
  if (!finished.value) {
    const used = new Set<string>()
    const rows: VisibleRow[] = []
    for (const block of props.msg.blocks) {
      if (block.type === 'approval') continue
      const hint = matchApprovalHint(block, props.msg.blocks, used)
      rows.push({ key: block.id, block, hint })
    }
    return rows
  }
  const blocks =
    !showCollapseChrome.value || workExpanded.value ? props.msg.blocks : answerBlocks.value
  return blocks.map((block) => ({ key: block.id, block }))
})

watch(finished, (done) => {
  if (done) workExpanded.value = false
})

function toggleWork() {
  workExpanded.value = !workExpanded.value
  emit('toggle')
}

function summaryLabel(): string {
  const blocks = [...workBlocks.value, ...collapsedMarkdown.value]
  let think = 0
  let tools = 0
  let files = 0
  let approvals = 0
  let other = 0
  for (const b of blocks) {
    if (b.type === 'approval') {
      approvals += 1
      continue
    }
    const kind = classifyBlock(b)
    if (kind === 'think') think += 1
    else if (kind === 'tool' || kind === 'context' || kind === 'terminal') tools += 1
    else if (kind === 'diff') files += 1
    else other += 1
  }
  const parts: string[] = []
  if (think) parts.push(`${think} 次思考`)
  if (tools) parts.push(`${tools} 次工具`)
  if (files) parts.push(`${files} 处变更`)
  if (approvals) parts.push(`${approvals} 次确认`)
  if (!parts.length) parts.push(`${blocks.length || other} 步`)
  return parts.join(' · ')
}
</script>

<template>
  <div class="assistant-body">
    <button
      v-if="showCollapseChrome"
      type="button"
      class="work-toggle"
      :aria-expanded="workExpanded"
      @click="toggleWork"
    >
      <AppIcon class="chev" name="chevron-right" :size="12" />
      <span class="work-label">{{ workExpanded ? '收起工作过程' : '工作过程' }}</span>
      <span class="work-meta">{{ summaryLabel() }}</span>
    </button>
    <template v-for="row in visibleRows" :key="row.key">
      <section class="block">
        <component :is="rendererFor(row.block.type)" :block="row.block as Block" />
      </section>
      <ApprovalInlineHint v-if="row.hint" :block="row.hint" />
    </template>
  </div>
</template>

<style scoped>
.assistant-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
}
.work-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  margin: 0 0 6px;
  padding: 4px 8px 4px 6px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.3;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}
.work-toggle:hover {
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--text-muted) 10%, transparent);
}
.work-toggle .chev {
  transition: transform 0.15s ease;
  opacity: 0.8;
}
.work-toggle[aria-expanded='true'] .chev {
  transform: rotate(90deg);
}
.work-label {
  font-weight: 560;
  color: var(--text-secondary);
}
.work-meta {
  color: var(--text-muted);
}
.block + .block {
  margin-top: 2px;
}
</style>
