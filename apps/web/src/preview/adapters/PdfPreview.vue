<script setup lang="ts">
import type { PreviewProps } from '@/preview/types'

defineProps<PreviewProps>()
</script>

<template>
  <div class="preview-pane pdf-preview">
    <iframe :src="previewUrl" title="PDF preview" />
  </div>
</template>

<style scoped>
.pdf-preview {
  width: 100%;
  height: 100%;
  background: var(--bg-muted);
}
iframe {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}
</style>
