<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NodeViewWrapper, type NodeViewProps } from '@tiptap/vue-3'
import AppIcon from '@/components/AppIcon.vue'
import { useAppStore } from '@/stores/app'

const props = defineProps<NodeViewProps>()
const store = useAppStore()
const { t } = useI18n()

const attrs = computed(() => props.node.attrs as {
  path: string
  name: string
  isDir: boolean
  lineStart: number | null
  lineEnd: number | null
})

const lineLabel = computed(() => {
  const start = attrs.value.lineStart
  const end = attrs.value.lineEnd
  if (!start || !end) return ''
  if (start === end) return `(${start})`
  return `(${start}-${end})`
})

function openMention() {
  const { path, isDir, lineStart } = attrs.value
  if (!path) return
  if (isDir) {
    void store.openPath(path, true)
    return
  }
  if (lineStart) {
    void store.openPathAtLine(path, lineStart)
    return
  }
  void store.openPath(path, false)
}

function removeMention() {
  props.deleteNode()
}
</script>

<template>
  <NodeViewWrapper
    as="span"
    class="file-mention-chip"
    :data-path="attrs.path"
    contenteditable="false"
  >
    <span
      class="file-mention-body"
      role="button"
      tabindex="0"
      @click.stop="openMention"
      @keydown.enter.prevent="openMention"
    >
      <AppIcon :name="attrs.isDir ? 'folder' : 'file'" :size="12" />
      <span class="file-mention-name">{{ attrs.name }}</span>
      <span v-if="lineLabel" class="file-mention-lines">{{ lineLabel }}</span>
    </span>
    <button
      type="button"
      class="file-mention-remove"
      :title="t('common.remove')"
      @mousedown.prevent
      @click.stop="removeMention"
    >
      <AppIcon name="close" :size="10" />
    </button>
  </NodeViewWrapper>
</template>

<style scoped>
.file-mention-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin: 0 2px;
  padding: 2px 2px 2px 8px;
  border-radius: 6px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 12px;
  font-family: var(--mono);
  font-weight: 500;
  white-space: nowrap;
  vertical-align: baseline;
  user-select: none;
  line-height: 1.4;
}
.file-mention-body {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  cursor: pointer;
}
.file-mention-body:hover {
  opacity: 0.85;
}
.file-mention-name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-mention-lines {
  color: var(--text-secondary);
  font-weight: 400;
}
.file-mention-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--primary);
  cursor: pointer;
  opacity: 0.65;
  flex-shrink: 0;
}
.file-mention-remove:hover {
  opacity: 1;
  background: var(--border);
}
</style>
