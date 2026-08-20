<script setup lang="ts">
import type { PreviewProps } from '@/preview/types'

defineProps<PreviewProps>()
</script>

<template>
  <div class="preview-pane image-preview">
    <img :src="previewUrl" :alt="path" />
  </div>
</template>

<style scoped>
.image-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  overflow: auto;
  padding: 16px;
  box-sizing: border-box;
  background:
    linear-gradient(45deg, var(--bg-muted) 25%, transparent 25%),
    linear-gradient(-45deg, var(--bg-muted) 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, var(--bg-muted) 75%),
    linear-gradient(-45deg, transparent 75%, var(--bg-muted) 75%);
  background-size: 16px 16px;
  background-position: 0 0, 0 8px, 8px -8px, -8px 0;
  background-color: var(--editor-bg);
}
img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  box-shadow: var(--shadow-md);
}
</style>
