<script setup lang="ts">
import type { PreviewProps } from '@/preview/types'

defineProps<PreviewProps>()
</script>

<template>
  <div class="preview-pane audio-preview">
    <div class="audio-card">
      <div class="audio-icon" aria-hidden="true">♫</div>
      <div class="audio-name" :title="path">{{ path.split('/').pop() || path }}</div>
      <audio :src="previewUrl" controls preload="metadata" />
    </div>
  </div>
</template>

<style scoped>
.audio-preview { display: grid; place-items: center; width: 100%; height: 100%; padding: 24px; box-sizing: border-box; }
.audio-card { width: min(560px, 100%); padding: 28px; border: 1px solid var(--border); border-radius: 16px; background: var(--bg-elevated); text-align: center; }
.audio-icon { margin-bottom: 10px; color: var(--primary); font-size: 42px; }
.audio-name { margin-bottom: 18px; overflow: hidden; color: var(--text-primary); text-overflow: ellipsis; white-space: nowrap; }
audio { width: 100%; }
</style>
