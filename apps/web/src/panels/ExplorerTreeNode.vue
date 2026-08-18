<script setup lang="ts">
import type { FsItem } from '@/stores/app'
import { useAppStore } from '@/stores/app'
import FileGlyph from '@/components/FileGlyph.vue'
import ExplorerTreeNode from '@/panels/ExplorerTreeNode.vue'

defineProps<{
  item: FsItem
  depth: number
}>()

const store = useAppStore()
const emit = defineEmits<{
  context: [e: MouseEvent, item: FsItem]
}>()
</script>

<template>
  <div class="node">
    <button
      type="button"
      class="row"
      :class="{ active: store.activePath === item.path }"
      :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
      @click="store.openPath(item.path, item.is_dir)"
      @contextmenu="emit('context', $event, item)"
    >
      <span class="twist" :class="{ on: item.is_dir && store.isExpanded(item.path), hidden: !item.is_dir }" />
      <FileGlyph :name="item.name" :is-dir="item.is_dir" :size="15" />
      <span class="label">{{ item.name }}</span>
    </button>
    <template v-if="item.is_dir && store.isExpanded(item.path)">
      <ExplorerTreeNode
        v-for="child in store.childrenOf(item.path)"
        :key="child.path"
        :item="child"
        :depth="depth + 1"
        @context="(e, it) => emit('context', e, it)"
      />
    </template>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 26px;
  border: 0;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  padding-right: 8px;
  font-size: 13px;
  text-align: left;
}
.row:hover { background: var(--bg-muted); }
.row.active { background: var(--primary-soft); color: var(--primary); }
.twist {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-right: 1.6px solid var(--text-muted);
  border-bottom: 1.6px solid var(--text-muted);
  transform: rotate(-45deg);
  margin: 0 2px 0 2px;
}
.twist.on { transform: rotate(45deg); margin-top: -2px; }
.twist.hidden { visibility: hidden; }
.label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
