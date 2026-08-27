<script setup lang="ts">
import type { PreviewProps } from '@/preview/types'
import ImageViewer from '@/components/ImageViewer.vue'

defineProps<PreviewProps>()
</script>

<template>
  <ImageViewer embedded :src="previewUrl" :alt="path" :title="path" />
</template>
