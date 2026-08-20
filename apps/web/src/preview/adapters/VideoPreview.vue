<script setup lang="ts">
import type { PreviewProps } from '@/preview/types'

defineProps<PreviewProps>()
</script>

<template>
  <div class="preview-pane video-preview">
    <video :src="previewUrl" controls controlsList="nodownload" />
  </div>
</template>

<style scoped>
.video-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 16px;
  box-sizing: border-box;
  background: #0b0d12;
}
video {
  max-width: 100%;
  max-height: 100%;
  outline: none;
}
</style>
