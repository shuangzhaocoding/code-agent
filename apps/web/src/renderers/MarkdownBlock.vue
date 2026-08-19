<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Block } from '@/protocol/applyEvent'

const props = defineProps<{ block: Block }>()
const html = computed(() => DOMPurify.sanitize(marked.parse(props.block.text || '') as string))
</script>

<template>
  <div class="md markdown-body">
    <div v-html="html" />
    <span v-if="block.status === 'streaming'" class="dots" aria-hidden="true"><i /><i /><i /></span>
  </div>
</template>

<style scoped>
.md {
  color: var(--text-h);
  font-size: 14px;
  line-height: 1.7;
}
.dots {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 6px 0 2px;
  color: var(--primary);
}
.dots i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  animation: typing 1.05s ease-in-out infinite;
}
.dots i:nth-child(2) { animation-delay: 0.15s; }
.dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes typing {
  0%, 80%, 100% { opacity: 0.25; }
  40% { opacity: 1; }
}
</style>
