<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Block } from '@/protocol/applyEvent'
import { useAppStore } from '@/stores/app'

const props = defineProps<{ block: Block }>()
const store = useAppStore()

function openMention(path: string) {
  store.openPath(path, false)
}

// Split text into segments: plain text parts and @path mentions
interface Segment {
  kind: 'text' | 'mention'
  value: string  // for text: html; for mention: the path string
}

const segments = computed<Segment[]>(() => {
  const raw = props.block.text || ''
  // Split on @-mentions that look like paths (no whitespace)
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
</script>

<template>
  <div class="user-text">
    <template v-for="(seg, i) in segments" :key="i">
      <span v-if="seg.kind === 'mention'" class="at-mention" role="button" tabindex="0" @click="openMention(seg.value)" @keydown.enter="openMention(seg.value)">
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
