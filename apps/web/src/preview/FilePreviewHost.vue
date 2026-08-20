<script setup lang="ts">
import { computed } from 'vue'
import type { OpenFile } from '@/stores/app'
import { resolvePreviewAdapter } from '@/preview/registry'

const props = defineProps<{
  file: OpenFile
}>()

const adapter = computed(() => resolvePreviewAdapter(props.file.kind))
</script>

<template>
  <component
    :is="adapter"
    v-if="adapter && file.previewUrl"
    class="file-preview-host"
    :path="file.path"
    :preview-url="file.previewUrl"
    :mime="file.mime"
    :kind="file.kind"
    :content="file.content"
    :dirty="file.dirty"
  />
  <div v-else class="preview-missing">无法预览此文件</div>
</template>

<style scoped>
.file-preview-host {
  width: 100%;
  height: 100%;
  min-height: 0;
}
.preview-missing {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
