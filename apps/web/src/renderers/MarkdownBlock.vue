<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Block } from '@/protocol/applyEvent'
import { useAppStore } from '@/stores/app'
import { extractPlanSteps } from '@/utils/parsePlan'
import PlanSteps from '@/components/PlanSteps.vue'
import { openImageLightbox } from '@/composables/useImageLightbox'
import { fileLinkFromClickTarget, linkifyFilePathsInHtml } from '@/utils/chatFileLinks'

const props = defineProps<{ block: Block }>()
const store = useAppStore()
const mdRoot = ref<HTMLElement | null>(null)

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

const purifyOpts = { ADD_ATTR: ['target', 'data-path', 'data-line', 'data-ca-file'] }

function toHtml(text: string) {
  if (!text.trim()) return ''
  const root = store.workspace?.root_path || ''
  const parsed = marked.parse(text, {
    breaks: props.block.type === 'user.text',
  }) as string
  const linked = linkifyFilePathsInHtml(parsed, root)
  return DOMPurify.sanitize(linked, purifyOpts)
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
  () => [props.block.text, props.block.status, props.block.type, store.workspace?.root_path] as const,
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

function onMdClick(e: MouseEvent) {
  const fileLink = fileLinkFromClickTarget(e.target)
  if (fileLink) {
    e.preventDefault()
    e.stopPropagation()
    void store.openChatFilePath(fileLink.path, fileLink.line)
    return
  }
  const target = e.target
  if (!(target instanceof HTMLImageElement)) return
  const root = mdRoot.value
  if (!root) return
  e.preventDefault()
  const imgs = Array.from(root.querySelectorAll('img'))
  const items = imgs.map((img) => ({
    src: img.currentSrc || img.src,
    alt: img.alt || '',
    title: img.alt || img.title || '',
  }))
  const index = imgs.indexOf(target)
  openImageLightbox(items, index >= 0 ? index : 0)
}
</script>

<template>
  <div ref="mdRoot" class="md" @click="onMdClick">
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
.md :deep(.markdown-body img) {
  cursor: zoom-in;
  max-width: 100%;
  border-radius: 8px;
}
</style>
