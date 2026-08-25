<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Block } from '@/protocol/applyEvent'
import { useAppStore } from '@/stores/app'
import { detectAttachmentFileTypeFromMeta } from '@/utils/fileTypes'

const props = defineProps<{ block: Block }>()
const store = useAppStore()

type AttachmentFile = { name: string; url: string; size?: number; type?: string }

function openMention(path: string) {
  store.openPath(path, false)
}

interface Segment {
  kind: 'text' | 'mention'
  value: string
}

const segments = computed<Segment[]>(() => {
  const raw = props.block.text || ''
  const parts = raw.split(/(@[^\s@]+)/g)
  return parts
    .filter((p) => p.length > 0)
    .map((p) => {
      if (/^@[^\s@]+$/.test(p)) {
        return { kind: 'mention' as const, value: p.slice(1) }
      }
      const html = DOMPurify.sanitize(marked.parse(p, { breaks: true }) as string)
      return { kind: 'text' as const, value: html }
    })
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
</script>

<template>
  <div class="user-text">
    <div v-if="imageFiles.length" class="user-images">
      <a
        v-for="(file, i) in imageFiles"
        :key="`${file.url}-${i}`"
        class="user-image"
        :href="file.url"
        target="_blank"
        rel="noopener noreferrer"
        :title="file.name"
      >
        <img :src="file.url" :alt="file.name || '图片'" loading="lazy" />
      </a>
    </div>
    <ul v-if="otherFiles.length" class="user-files">
      <li v-for="(file, i) in otherFiles" :key="`${file.url}-${i}`">
        <a :href="file.url" target="_blank" rel="noopener noreferrer">{{ file.name || '附件' }}</a>
      </li>
    </ul>
    <template v-for="(seg, i) in segments" :key="i">
      <span
        v-if="seg.kind === 'mention'"
        class="at-mention"
        role="button"
        tabindex="0"
        @click="openMention(seg.value)"
        @keydown.enter="openMention(seg.value)"
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        {{ seg.value }}
      </span>
      <div v-else class="markdown-body" v-html="seg.value" />
    </template>
  </div>
</template>

<style scoped>
.user-text {
  color: var(--text-h);
  font-size: 14px;
  line-height: 1.7;
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
</style>
