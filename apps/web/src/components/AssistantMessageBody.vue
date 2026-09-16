<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { rendererFor } from '@/renderers'
import type { Block, ChatMessage } from '@/protocol/applyEvent'
import { matchApprovalHint } from '@/utils/approvals'
import { classifyBlock, isAnswerMarkdown, isConversationBlock } from '@/utils/trajectory'
import AppIcon from '@/components/AppIcon.vue'
import ApprovalInlineHint from '@/components/ApprovalInlineHint.vue'
import TodoBlock from '@/renderers/TodoBlock.vue'

const props = defineProps<{
  msg: ChatMessage
  /** True while this message's run is still streaming. */
  streaming?: boolean
}>()

const emit = defineEmits<{ toggle: [] }>()
const { t } = useI18n()

const workExpanded = ref(false)
const workToggleEl = ref<HTMLElement | null>(null)

const finished = computed(() => !props.streaming)

const lastTodoId = computed(() => {
  const last = [...props.msg.blocks].reverse().find((b) => b.type === 'todo')
  return last?.id || ''
})

const workBlocks = computed(() =>
  props.msg.blocks.filter((b) => {
    if (b.type === 'error') return false
    // Live todo is pinned above the composer; finished todo stays in the answer.
    if (b.type === 'todo') return false
    if (b.type === 'context.injected') return false
    if (b.type === 'approval') return finished.value
    return !isConversationBlock(b.type)
  }),
)

const answerBlocks = computed(() => {
  const lastTodo = lastTodoId.value
  const isAnswer = (b: Block) =>
    (b.type === 'assistant.markdown' && isAnswerMarkdown(b)) ||
    b.type === 'error' ||
    b.type === 'user.text' ||
    (finished.value && b.type === 'todo' && b.id === lastTodo)

  const candidates = props.msg.blocks.filter(
    (b) => (b.type === 'assistant.markdown' && isAnswerMarkdown(b as Block)) || b.type === 'error',
  )
  if (!finished.value) {
    return props.msg.blocks.filter(
      (b) =>
        b.type !== 'approval' &&
        b.type !== 'todo' &&
        (isConversationBlock(b.type) || b.type === 'error'),
    )
  }
  if (candidates.length <= 1) {
    return props.msg.blocks.filter((b) => b.type !== 'approval' && isAnswer(b as Block))
  }
  const lastMd = candidates[candidates.length - 1]
  return props.msg.blocks.filter(
    (b) =>
      b.type === 'error' ||
      b.type === 'user.text' ||
      (b.type === 'todo' && b.id === lastTodo) ||
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
      if (block.type === 'approval' || block.type === 'todo' || block.type === 'context.injected') continue
      const hint = matchApprovalHint(block, props.msg.blocks, used)
      rows.push({ key: block.id, block, hint })
    }
    return rows
  }
  const lastTodo = lastTodoId.value
  const blocks =
    !showCollapseChrome.value || workExpanded.value
      ? props.msg.blocks.filter(
          (b) =>
            (b.type !== 'todo' || b.id === lastTodo) && b.type !== 'context.injected',
        )
      : answerBlocks.value
  return blocks.map((block) => ({ key: block.id, block }))
})

watch(finished, (done) => {
  if (done) workExpanded.value = false
})

async function toggleWork(fromBottom = false) {
  const collapsing = workExpanded.value
  workExpanded.value = !workExpanded.value
  emit('toggle')
  if (collapsing && fromBottom) {
    await nextTick()
    workToggleEl.value?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }
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
    if (b.type === 'todo') continue
    const kind = classifyBlock(b)
    if (kind === 'think') think += 1
    else if (kind === 'tool' || kind === 'context' || kind === 'terminal') tools += 1
    else if (kind === 'diff') files += 1
    else other += 1
  }
  const parts: string[] = []
  if (think) parts.push(t('chat.thinkCount', { n: think }))
  if (tools) parts.push(t('chat.toolCount', { n: tools }))
  if (files) parts.push(t('chat.fileCount', { n: files }))
  if (approvals) parts.push(t('chat.approvalCount', { n: approvals }))
  if (!parts.length) parts.push(t('chat.stepCount', { n: blocks.length || other }))
  return parts.join(' · ')
}
</script>

<template>
  <div class="assistant-body">
    <button
      v-if="showCollapseChrome"
      ref="workToggleEl"
      type="button"
      class="work-toggle"
      :aria-expanded="workExpanded"
      @click="toggleWork(false)"
    >
      <AppIcon class="chev" name="chevron-right" :size="12" />
      <span class="work-label">{{ workExpanded ? t('chat.hideWork') : t('chat.workProcess') }}</span>
      <span class="work-meta">{{ summaryLabel() }}</span>
    </button>
    <template v-for="row in visibleRows" :key="row.key">
      <section class="block">
        <TodoBlock
          v-if="row.block.type === 'todo'"
          :block="row.block as Block"
          :default-collapsed="true"
        />
        <component :is="rendererFor(row.block.type)" v-else :block="row.block as Block" />
      </section>
      <ApprovalInlineHint v-if="row.hint" :block="row.hint" />
    </template>
    <button
      v-if="showCollapseChrome && workExpanded"
      type="button"
      class="work-toggle work-toggle-bottom"
      :aria-expanded="true"
      @click="toggleWork(true)"
    >
      <AppIcon class="chev" name="chevron-up" :size="12" />
      <span class="work-label">{{ t('chat.hideWork') }}</span>
    </button>
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
.work-toggle-bottom {
  margin: 8px 0 0;
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
.work-toggle-bottom[aria-expanded='true'] .chev {
  transform: none;
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
