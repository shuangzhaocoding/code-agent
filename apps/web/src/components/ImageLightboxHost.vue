<script setup lang="ts">
import { computed } from 'vue'
import ImageViewer from '@/components/ImageViewer.vue'
import { closeImageLightbox, useImageLightbox } from '@/composables/useImageLightbox'

const { state } = useImageLightbox()

const open = computed({
  get: () => state.open,
  set: (value: boolean) => {
    if (!value) closeImageLightbox()
  },
})

const index = computed({
  get: () => state.index,
  set: (value: number) => {
    state.index = value
  },
})
</script>

<template>
  <ImageViewer
    v-if="state.items.length"
    v-model:open="open"
    v-model:index="index"
    :items="state.items"
  />
</template>
