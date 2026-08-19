<script setup lang="ts">
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { resolveFileTreeIcon } from '@/utils/fileTreeIcon'

const props = defineProps<{
  kind: 'file' | 'dir'
  path: string
  expanded?: boolean
  size?: number | string
}>()

const icon = computed(() => resolveFileTreeIcon(props.kind, props.path, props.expanded))
const px = computed(() => Number(props.size) || 16)
</script>

<template>
  <Icon
    class="file-tree-icon"
    :icon="icon"
    :width="px"
    :height="px"
  />
</template>

<style scoped>
.file-tree-icon {
  display: block;
  flex-shrink: 0;
  color: unset;
  pointer-events: none;
}

.file-tree-icon :deep(svg) {
  display: block;
}
</style>
