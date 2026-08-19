<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { FsItem } from '@/stores/app'
import { useAppStore } from '@/stores/app'
import FileTreeIcon from '@/components/FileTreeIcon.vue'
import ExplorerTreeNode from '@/panels/ExplorerTreeNode.vue'

const props = defineProps<{
  item: FsItem
  depth: number
  renamingPath?: string | null
}>()

const store = useAppStore()
const mark = computed(() => store.fileTreeMark(props.item.path, props.item.is_dir))
const emit = defineEmits<{
  context: [e: MouseEvent, item: FsItem]
  'start-rename': [path: string]
  'commit-rename': [from: string, newName: string]
  'cancel-rename': []
}>()

const renameVal = ref('')
const renameInput = ref<HTMLInputElement | null>(null)
const isRenaming = computed(() => props.renamingPath === props.item.path)

watch(isRenaming, (v) => {
  if (v) {
    renameVal.value = props.item.name
    nextTick(() => {
      renameInput.value?.focus()
      renameInput.value?.select()
    })
  }
})

function commitRename() {
  const name = renameVal.value.trim()
  if (name && name !== props.item.name) {
    emit('commit-rename', props.item.path, name)
  } else {
    emit('cancel-rename')
  }
}
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
      <FileTreeIcon
        :kind="item.is_dir ? 'dir' : 'file'"
        :path="item.path"
        :expanded="store.isExpanded(item.path)"
        :size="16"
      />
      <input
        v-if="isRenaming"
        ref="renameInput"
        v-model="renameVal"
        class="rename-input"
        @blur="commitRename"
        @keydown.enter.prevent="commitRename"
        @keydown.escape.prevent="emit('cancel-rename')"
        @click.stop
      />
      <span v-else class="label">{{ item.name }}</span>
      <span
        v-if="mark.show"
        class="tree-dot"
        :title="mark.title"
        :aria-label="mark.title"
      />
    </button>
    <template v-if="item.is_dir && store.isExpanded(item.path)">
      <ExplorerTreeNode
        v-for="child in store.childrenOf(item.path)"
        :key="child.path"
        :item="child"
        :depth="depth + 1"
        :renaming-path="renamingPath"
        @context="(e, it) => emit('context', e, it)"
        @start-rename="(p) => emit('start-rename', p)"
        @commit-rename="(from, name) => emit('commit-rename', from, name)"
        @cancel-rename="emit('cancel-rename')"
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
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rename-input {
  flex: 1;
  min-width: 0;
  height: 20px;
  font-size: 13px;
  padding: 0 4px;
  border: 1px solid var(--primary);
  border-radius: 3px;
  background: var(--bg);
  color: var(--text);
  outline: none;
  font-family: inherit;
}
.tree-dot {
  width: 6px;
  height: 6px;
  margin-left: auto;
  border-radius: 99px;
  background: var(--primary);
  flex-shrink: 0;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 18%, transparent);
}
</style>
