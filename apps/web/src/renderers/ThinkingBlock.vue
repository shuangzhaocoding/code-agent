<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { scrollToBottom } from '@/utils/smoothScroll'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'

const props = defineProps<{ block: Block }>()
const streaming = computed(() => props.block.status === 'streaming')
const bodyEl = ref<HTMLElement | null>(null)
const html = ref('')
const elapsed = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
let renderTimer: ReturnType<typeof setTimeout> | null = null
let renderRaf = 0
let lastRenderAt = 0
let scrollRaf = 0
const STREAM_RENDER_MS = 80

function toMs(v: number | string | undefined): number {
  if (!v) return 0
  if (typeof v === 'number') return v
  return new Date(v).getTime()
}

function updateElapsed() {
  const start = toMs(props.block.started_at)
  if (!start) return
  const end = toMs(props.block.ended_at) || Date.now()
  elapsed.value = Math.round((end - start) / 100) / 10
}

function renderNow(text: string) {
  const source = text || (streaming.value ? '正在思考…' : '（无内容）')
  html.value = DOMPurify.sanitize(
    marked.parse(source, { breaks: true }) as string,
  )
  lastRenderAt = Date.now()
  if (scrollRaf) return
  scrollRaf = requestAnimationFrame(() => {
    scrollRaf = 0
    const el = bodyEl.value
    if (el) scrollToBottom(el, 'auto')
  })
}

function scheduleStreamRender() {
  if (renderRaf || renderTimer) return
  const wait = Math.max(0, STREAM_RENDER_MS - (Date.now() - lastRenderAt))
  if (wait === 0) {
    renderRaf = requestAnimationFrame(() => {
      renderRaf = 0
      renderNow(props.block.text || '')
    })
    return
  }
  renderTimer = setTimeout(() => {
    renderTimer = null
    renderNow(props.block.text || '')
  }, wait)
}

function clearRenderSchedulers() {
  if (renderTimer) {
    clearTimeout(renderTimer)
    renderTimer = null
  }
  if (renderRaf) {
    cancelAnimationFrame(renderRaf)
    renderRaf = 0
  }
}

onMounted(() => {
  updateElapsed()
  timer = setInterval(updateElapsed, 500)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  clearRenderSchedulers()
})

watch(() => props.block.status, () => {
  updateElapsed()
  if (!streaming.value && timer) {
    clearInterval(timer)
    timer = null
  }
})

watch(
  () => [props.block.text, props.block.status] as const,
  ([text, status]) => {
    if (status === 'streaming') {
      if (Date.now() - lastRenderAt >= STREAM_RENDER_MS) {
        clearRenderSchedulers()
        renderNow(text || '')
      } else {
        scheduleStreamRender()
      }
      return
    }
    clearRenderSchedulers()
    renderNow(text || '')
  },
  { immediate: true },
)

const timeLabel = computed(() => {
  if (!toMs(props.block.started_at)) return ''
  return `${elapsed.value.toFixed(1)}s`
})

const subtitle = computed(() => {
  if (streaming.value) return `正在思考… ${timeLabel.value}`
  if (props.block.text) return `已生成思考内容（${timeLabel.value}）`
  return ''
})
</script>

<template>
  <EventCard
    icon="think"
    title="思考过程"
    tone="think"
    :status="block.status"
    :default-open="false"
    :subtitle="subtitle"
  >
    <div ref="bodyEl" class="think-body">
      <div class="markdown-body" v-html="html" />
      <span v-if="streaming" class="caret" />
    </div>
  </EventCard>
</template>

<style scoped>
.think-body {
  max-height: 360px;
  overflow: auto;
  color: var(--text-secondary);
  font-size: 12.5px;
  line-height: 1.65;
}
.think-body :deep(.markdown-body) {
  color: inherit;
  font-size: inherit;
}
.think-body :deep(.markdown-body p:first-child) { margin-top: 0; }
.think-body :deep(.markdown-body p:last-child) { margin-bottom: 0; }
.think-body :deep(.markdown-body code) {
  font-size: 0.92em;
}
.caret {
  display: inline-block;
  width: 6px;
  height: 12px;
  margin-left: 2px;
  background: #8b5cf6;
  vertical-align: -1px;
  animation: blink 1s step-end infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
</style>
