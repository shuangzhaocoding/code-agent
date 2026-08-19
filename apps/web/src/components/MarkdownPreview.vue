<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { extractMarkdownToc } from '@/utils/markdownToc'

const props = defineProps<{ content: string; path?: string }>()

const stageRef = ref<HTMLElement | null>(null)
const bodyRef = ref<HTMLElement | null>(null)
const activeId = ref('')
let observer: IntersectionObserver | null = null

const html = computed(() => DOMPurify.sanitize(marked.parse(props.content || '') as string))
const toc = computed(() => extractMarkdownToc(props.content))
const minLevel = computed(() => {
  if (!toc.value.length) return 1
  return Math.min(...toc.value.map((item) => item.level))
})

function ensureHeadingIds() {
  const root = bodyRef.value
  if (!root || !toc.value.length) return
  const headings = Array.from(root.querySelectorAll('h1, h2, h3, h4, h5, h6')) as HTMLElement[]
  toc.value.forEach((item, index) => {
    const el = headings[index]
    if (!el) return
    el.id = item.id
  })
}

function observeHeadings() {
  observer?.disconnect()
  observer = null
  const root = bodyRef.value
  const stage = stageRef.value
  if (!root || !stage || !toc.value.length) return

  observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      const first = visible[0]?.target as HTMLElement | undefined
      if (first?.id) activeId.value = first.id
    },
    {
      root: stage,
      rootMargin: '0px 0px -70% 0px',
      threshold: [0, 1],
    },
  )
  toc.value.forEach((item) => {
    const node = root.querySelector(`#${CSS.escape(item.id)}`)
    if (node) observer?.observe(node)
  })
}

async function syncOutline() {
  await nextTick()
  ensureHeadingIds()
  if (!activeId.value && toc.value[0]) activeId.value = toc.value[0].id
  if (activeId.value && !toc.value.some((item) => item.id === activeId.value)) {
    activeId.value = toc.value[0]?.id ?? ''
  }
  observeHeadings()
}

function scrollToHeading(id: string) {
  const root = bodyRef.value
  if (!root) return
  ensureHeadingIds()
  const target = root.querySelector(`#${CSS.escape(id)}`) as HTMLElement | null
  if (!target) return
  activeId.value = id
  target.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onBodyClick(event: MouseEvent) {
  const anchor = (event.target as HTMLElement | null)?.closest?.('a')
  if (!anchor) return
  const href = anchor.getAttribute('href') || ''
  if (!href.startsWith('#')) return
  event.preventDefault()
  const id = decodeURIComponent(href.slice(1))
  if (id) scrollToHeading(id)
}

watch(
  () => props.path,
  () => {
    activeId.value = ''
  },
)

watch(html, () => {
  void syncOutline()
})

watch(toc, () => {
  void syncOutline()
})

onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>

<template>
  <div class="md-preview">
    <aside v-if="toc.length" class="md-preview__toc" aria-label="目录">
      <div class="md-preview__toc-title">目录</div>
      <nav class="md-preview__toc-list">
        <button
          v-for="item in toc"
          :key="item.id"
          type="button"
          class="md-preview__toc-item"
          :class="{ 'is-active': item.id === activeId }"
          :style="{ paddingLeft: `${10 + (item.level - minLevel) * 12}px` }"
          :title="item.text"
          @click="scrollToHeading(item.id)"
        >
          {{ item.text }}
        </button>
      </nav>
    </aside>
    <div ref="stageRef" class="md-preview__stage">
      <article
        ref="bodyRef"
        class="markdown-body md-preview__body"
        v-html="html"
        @click="onBodyClick"
      />
    </div>
  </div>
</template>

<style scoped>
.md-preview {
  display: flex;
  flex-direction: row;
  width: 100%;
  height: 100%;
  min-width: 0;
  background: var(--panel-bg);
}

.md-preview__toc {
  display: flex;
  flex-direction: column;
  flex: 0 0 220px;
  width: 220px;
  min-width: 160px;
  max-width: 280px;
  border-right: var(--border-width) solid var(--border);
  background: var(--panel-bg);
}

.md-preview__toc-title {
  flex-shrink: 0;
  padding: 12px 14px 8px;
  color: var(--text);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.md-preview__toc-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 8px 12px;
}

.md-preview__toc-item {
  display: block;
  width: 100%;
  margin: 0;
  padding: 5px 10px;
  overflow: hidden;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 12px;
  line-height: 1.4;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.md-preview__toc-item:hover {
  background: var(--code-bg);
  color: var(--text-h);
}

.md-preview__toc-item.is-active {
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 600;
}

.md-preview__stage {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 20px 24px 32px;
  background: var(--panel-bg);
  scroll-behavior: smooth;
}

.md-preview__body {
  max-width: 760px;
  margin: 0 auto;
}

.md-preview__body :deep(h1[id]),
.md-preview__body :deep(h2[id]),
.md-preview__body :deep(h3[id]),
.md-preview__body :deep(h4[id]),
.md-preview__body :deep(h5[id]),
.md-preview__body :deep(h6[id]) {
  scroll-margin-top: 12px;
}

@media (max-width: 900px) {
  .md-preview__toc {
    flex-basis: 168px;
    width: 168px;
  }
}
</style>
