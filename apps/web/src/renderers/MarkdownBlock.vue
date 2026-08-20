<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Block } from '@/protocol/applyEvent'

const props = defineProps<{ block: Block }>()

const html = ref('')
let timer: ReturnType<typeof setTimeout> | null = null
let raf = 0
let lastRenderAt = 0
/** Keep markdown while streaming; coalesce parse to ~1–2 frames. */
const STREAM_RENDER_MS = 32

function renderNow(text: string) {
  html.value = DOMPurify.sanitize(
    marked.parse(text || '', {
      breaks: props.block.type === 'user.text',
    }) as string,
  )
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
    <div class="markdown-body" v-html="html" />
  </div>
</template>

<style scoped>
.md {
  color: var(--text-h);
  font-size: 14px;
  line-height: 1.65;
}
.md :deep(.markdown-body p:first-child) {
  margin-top: 0;
}
.md :deep(.markdown-body p:last-child) {
  margin-bottom: 0;
}
</style>
