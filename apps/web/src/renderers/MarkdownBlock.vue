<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Block } from '@/protocol/applyEvent'

const props = defineProps<{ block: Block }>()
const html = computed(() =>
  DOMPurify.sanitize(
    marked.parse(props.block.text || '', {
      breaks: props.block.type === 'user.text',
    }) as string,
  ),
)
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
