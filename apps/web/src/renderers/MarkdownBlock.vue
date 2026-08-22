<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Block } from '@/protocol/applyEvent'
import { useAppStore } from '@/stores/app'
import { extractPlanSteps } from '@/utils/parsePlan'
import PlanSteps from '@/components/PlanSteps.vue'

const props = defineProps<{ block: Block }>()
const store = useAppStore()

const html = ref('')
const beforeHtml = ref('')
const afterHtml = ref('')
const plan = computed(() =>
  store.mode === 'plan' || /计划|任务步骤|实施步骤/.test(props.block.text || '')
    ? extractPlanSteps(props.block.text || '')
    : null,
)
let timer: ReturnType<typeof setTimeout> | null = null
let raf = 0
let lastRenderAt = 0
/** Keep markdown while streaming; coalesce parse to ~1–2 frames. */
const STREAM_RENDER_MS = 80

function toHtml(text: string) {
  if (!text.trim()) return ''
  return DOMPurify.sanitize(
    marked.parse(text, {
      breaks: props.block.type === 'user.text',
    }) as string,
  )
}

function renderNow(text: string) {
  const parsed = store.mode === 'plan' || /计划|任务步骤|实施步骤/.test(text || '')
    ? extractPlanSteps(text || '')
    : null
  if (parsed) {
    html.value = ''
    beforeHtml.value = toHtml(parsed.before)
    afterHtml.value = toHtml(parsed.after)
  } else {
    html.value = toHtml(text || '')
    beforeHtml.value = ''
    afterHtml.value = ''
  }
  lastRenderAt = Date.now()
}

function scheduleStreamRender() {
  if (raf || timer) return
  const wait = Math.max(0, STREAM_RENDER_MS - (Date.now() - lastRenderAt))
  if (wait === 0) {
    raf = requestAnimationFrame(() => {
      raf = 0
      renderNow(props.block.text || '')
    })
    return
  }
  timer = setTimeout(() => {
    timer = null
    renderNow(props.block.text || '')
  }, wait)
}

function clearSchedulers() {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
  if (raf) {
    cancelAnimationFrame(raf)
    raf = 0
  }
}

watch(
  () => [props.block.text, props.block.status, props.block.type] as const,
  ([text, status]) => {
    if (status === 'streaming') {
      if (Date.now() - lastRenderAt >= STREAM_RENDER_MS) {
        clearSchedulers()
        renderNow(text || '')
      } else {
        scheduleStreamRender()
      }
      return
    }
    clearSchedulers()
    renderNow(text || '')
  },
  { immediate: true },
)

onBeforeUnmount(clearSchedulers)
</script>

<template>
  <div class="md">
    <div v-if="beforeHtml" class="markdown-body" v-html="beforeHtml" />
    <PlanSteps v-if="plan?.steps.length" :steps="plan.steps" />
    <div v-if="afterHtml" class="markdown-body" v-html="afterHtml" />
    <div v-if="html" class="markdown-body" v-html="html" />
  </div>
</template>

<style scoped>
.md {
  color: var(--text-h);
  font-size: 14px;
  line-height: 1.65;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.md :deep(.markdown-body p:first-child) {
  margin-top: 0;
}
.md :deep(.markdown-body p:last-child) {
  margin-bottom: 0;
}
</style>
