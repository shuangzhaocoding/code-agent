<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { PreviewProps } from '@/preview/types'

const props = defineProps<PreviewProps>()
const blobUrl = ref<string | null>(null)

function revoke() {
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = null
  }
}

function syncBlob() {
  revoke()
  // Dirty / in-editor edits: preview current source via blob
  if (props.dirty && typeof props.content === 'string') {
    const blob = new Blob([props.content], { type: 'text/html;charset=utf-8' })
    blobUrl.value = URL.createObjectURL(blob)
  }
}

watch(
  () => [props.content, props.dirty, props.previewUrl] as const,
  () => syncBlob(),
  { immediate: true },
)

onBeforeUnmount(revoke)

const frameSrc = computed(() => {
  if (props.dirty && blobUrl.value) return blobUrl.value
  return props.previewUrl
})
</script>

<template>
  <div class="preview-pane html-preview">
    <iframe
      :src="frameSrc"
      title="HTML preview"
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
    />
  </div>
</template>

<style scoped>
.html-preview {
  width: 100%;
  height: 100%;
  background: #fff;
}
iframe {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
  background: #fff;
}
</style>
