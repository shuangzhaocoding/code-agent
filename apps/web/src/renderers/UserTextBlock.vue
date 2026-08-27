<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Block } from '@/protocol/applyEvent'
import { useAppStore } from '@/stores/app'
import { detectAttachmentFileTypeFromMeta } from '@/utils/fileTypes'
import { openImageLightbox } from '@/composables/useImageLightbox'
import SkillMentionChip from '@/components/SkillMentionChip.vue'

const props = defineProps<{ block: Block }>()
const store = useAppStore()

type AttachmentFile = { name: string; url: string; size?: number; type?: string }

function openImagePreview(index: number) {
  const items = imageFiles.value.map((item) => ({
    src: item.url,
    alt: item.name || '',
    title: item.name || '',
  }))
  openImageLightbox(items, index)
}

function resolveMentionIsDir(path: string) {
  if (store.childrenMap[path]) return true
  const parent = store.parentPath(path)
  const item = store.childrenOf(parent).find((i) => i.path === path)
  return item?.is_dir ?? false
}

function openMention(path: string, isDir = false) {
  void store.openPath(path, isDir)
}

type Segment = {
  kind: 'text' | 'mention'
  value: string
  name?: string
  lineLabel?: string
  isDir?: boolean
}

function inlineTextHtml(text: string) {
  if (!text) return ''
  if (!text.trim()) return text.replace(/ /g, '&nbsp;')
  return text
    .split('\n')
    .map((line) => {
      if (!line.trim()) return '<br>'
      return DOMPurify.sanitize(marked.parseInline(line, { breaks: true }) as string)
    })
    .join('<br>')
}

const segments = computed<Segment[]>(() => {
  const raw = props.block.text || ''
  const parts = raw.split(/(@[^\s@]+(?::\d+(?:-\d+)?)?)/g)
  return parts
    .filter((p) => p.length > 0)
    .map((p) => {
      const match = /^@([^\s@]+)(?::(\d+)(?:-(\d+))?)?$/.exec(p)
      if (match) {
        const path = match[1]
        const lineStart = match[2] ? Number(match[2]) : null
        const lineEnd = match[3] ? Number(match[3]) : lineStart
        const name = path.split('/').filter(Boolean).pop() || path
        const lineLabel = lineStart
          ? lineStart === lineEnd
            ? `(${lineStart})`
            : `(${lineStart}-${lineEnd})`
          : ''
        const isDir = !lineStart && resolveMentionIsDir(path)
        return { kind: 'mention' as const, value: path, name, lineLabel, isDir }
      }
      return { kind: 'text' as const, value: inlineTextHtml(p) }
    })
})

const hasInlineMentions = computed(() => segments.value.some((s) => s.kind === 'mention'))

const plainHtml = computed(() => {
  const raw = props.block.text || ''
  return DOMPurify.sanitize(marked.parse(raw, { breaks: true }) as string)
})

const files = computed<AttachmentFile[]>(() => {
  const meta = (props.block.meta || {}) as { files?: AttachmentFile[] }
  return Array.isArray(meta.files) ? meta.files.filter((f) => f?.url) : []
})

const imageFiles = computed(() =>
  files.value.filter((f) => detectAttachmentFileTypeFromMeta(f.name || '', f.type || '') === 'image'),
)

const otherFiles = computed(() =>
  files.value.filter((f) => detectAttachmentFileTypeFromMeta(f.name || '', f.type || '') !== 'image'),
)

const skillName = computed(() => {
  const meta = (props.block.meta || {}) as { skill?: { name?: string } }
  return meta.skill?.name || ''
})
</script>

<template>
  <div class="user-text">
    <div v-if="imageFiles.length" class="user-images">
      <button
        v-for="(file, i) in imageFiles"
        :key="`${file.url}-${i}`"
        type="button"
        class="user-image"
        :title="file.name"
        @click="openImagePreview(i)"
      >
        <img :src="file.url" :alt="file.name || '图片'" loading="lazy" />
      </button>
    </div>
    <ul v-if="otherFiles.length" class="user-files">
      <li v-for="(file, i) in otherFiles" :key="`${file.url}-${i}`">
        <a :href="file.url" target="_blank" rel="noopener noreferrer">{{ file.name || '附件' }}</a>
      </li>
    </ul>
    <div v-if="skillName || hasInlineMentions" class="user-text-inline">
      <SkillMentionChip v-if="skillName" :name="skillName" />
      <template v-for="(seg, i) in segments" :key="i">
        <span
          v-if="seg.kind === 'mention'"
          class="at-mention"
          role="button"
          tabindex="0"
          @click="openMention(seg.value, seg.isDir)"
          @keydown.enter="openMention(seg.value, seg.isDir)"
        >
          <svg v-if="seg.isDir" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <svg v-else width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          {{ seg.name || seg.value }}<span v-if="seg.lineLabel" class="at-mention-lines">{{ seg.lineLabel }}</span>
        </span>
        <span v-else-if="seg.value" class="markdown-inline" v-html="seg.value" />
      </template>
    </div>
    <div v-else-if="segments.length" class="markdown-body" v-html="plainHtml" />
  </div>
</template>

<style scoped>
.user-text {
  color: var(--text-h);
  font-size: 14px;
  line-height: 1.7;
}
.user-text-inline {
  display: inline;
  line-height: 1.7;
}
.user-text-inline :deep(.skill-mention-chip.readonly) {
  vertical-align: middle;
  margin: 0 2px;
  padding: 1px 7px 1px 5px;
  border-radius: 5px;
  line-height: 1.4;
}
.markdown-inline :deep(p) {
  display: inline;
  margin: 0;
}
.markdown-inline :deep(br) {
  display: inline;
}
.user-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.user-image {
  display: block;
  max-width: min(280px, 100%);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--bg-muted);
  line-height: 0;
  padding: 0;
  cursor: zoom-in;
}
.user-image:hover {
  border-color: var(--primary);
}
.user-image img {
  display: block;
  max-width: 100%;
  max-height: 220px;
  width: auto;
  height: auto;
  object-fit: contain;
}
.user-files {
  margin: 0 0 8px;
  padding: 0;
  list-style: none;
  font-size: 12px;
}
.user-files a {
  color: var(--primary);
  text-decoration: none;
}
.user-files a:hover { text-decoration: underline; }
.at-mention {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 7px 1px 5px;
  border-radius: 5px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 12px;
  font-family: var(--mono);
  font-weight: 500;
  white-space: nowrap;
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
  margin: 0 2px;
  cursor: pointer;
  transition: opacity 0.12s;
}
.at-mention:hover { opacity: 0.75; }
.at-mention-lines {
  margin-left: 2px;
  color: var(--text-secondary);
  font-weight: 400;
}
</style>
