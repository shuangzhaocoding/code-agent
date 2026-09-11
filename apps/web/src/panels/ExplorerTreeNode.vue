<script setup lang="ts">
import { computed, inject, nextTick, onUnmounted, ref, watch } from 'vue'
import type { FsItem } from '@/stores/app'
import { useAppStore } from '@/stores/app'
import FileTreeIcon from '@/components/FileTreeIcon.vue'
import ExplorerTreeNode from '@/panels/ExplorerTreeNode.vue'
import ExplorerCreateRow from '@/panels/ExplorerCreateRow.vue'
import { explorerDragKey, FS_DRAG_MIME, isOsFileDrag } from '@/panels/explorerDrag'

const props = defineProps<{
  item: FsItem
  depth: number
  renamingPath?: string | null
  creating?: { kind: 'file' | 'dir'; dir: string; value: string; id: number } | null
}>()

const store = useAppStore()
const drag = inject(explorerDragKey, null)
const mark = computed(() => store.fileTreeMark(props.item.path, props.item.is_dir))
const isCut = computed(() => {
  const clip = store.fsClipboard
  if (!clip || clip.mode !== 'cut' || clip.workspace_id !== store.workspaceId) return false
  const src = clip.path
  return props.item.path === src || props.item.path.startsWith(`${src}/`)
})
const isDragging = computed(() => drag?.dragSrc.value?.path === props.item.path)
const isDropTarget = computed(() => drag?.dropHoverPath.value === props.item.path)
const isDropExpandHover = computed(
  () => props.item.is_dir && drag?.dropHoverPath.value === props.item.path,
)
const emit = defineEmits<{
  context: [e: MouseEvent, item: FsItem]
  select: [item: FsItem]
  'start-rename': [path: string]
  'commit-rename': [from: string, newName: string]
  'cancel-rename': []
  'update:creating': [value: string]
  'commit-create': []
  'cancel-create': []
}>()

const renameVal = ref('')
const renameInput = ref<HTMLInputElement | null>(null)
const isRenaming = computed(() => props.renamingPath === props.item.path)
let suppressClick = false
let expandTimer: ReturnType<typeof setTimeout> | null = null

watch(isRenaming, (v) => {
  if (v) {
    renameVal.value = props.item.name
    nextTick(() => {
      renameInput.value?.focus()
      renameInput.value?.select()
    })
  }
})

watch(
  () => isDropExpandHover.value,
  (shouldExpand) => {
    if (expandTimer) {
      clearTimeout(expandTimer)
      expandTimer = null
    }
    if (!shouldExpand) return
    if (store.isExpanded(props.item.path)) return
    expandTimer = setTimeout(() => {
      void store.expandDir(props.item.path)
      expandTimer = null
    }, 650)
  },
)

onUnmounted(() => {
  if (expandTimer) clearTimeout(expandTimer)
})

function commitRename() {
  const name = renameVal.value.trim()
  if (name && name !== props.item.name) {
    emit('commit-rename', props.item.path, name)
  } else {
    emit('cancel-rename')
  }
}

function onRowClick() {
  if (suppressClick) {
    suppressClick = false
    return
  }
  emit('select', props.item)
  store.openPath(props.item.path, props.item.is_dir)
}

function onDragStart(e: DragEvent) {
  if (!drag || isRenaming.value) {
    e.preventDefault()
    return
  }
  const dt = e.dataTransfer
  if (!dt) return
  dt.effectAllowed = 'move'
  dt.setData(FS_DRAG_MIME, JSON.stringify({ path: props.item.path, is_dir: props.item.is_dir }))
  dt.setData('text/plain', props.item.path)
  drag.beginDrag(props.item)
  suppressClick = true
}

function onDragEnd() {
  drag?.endDrag()
  nextTick(() => {
    // Keep suppressClick through the trailing click after a drag.
    setTimeout(() => {
      suppressClick = false
    }, 0)
  })
}

function onDragOver(e: DragEvent) {
  if (!drag) return
  const types = e.dataTransfer?.types
  const isOurs = !!drag.dragSrc.value || (types != null && [...types].includes(FS_DRAG_MIME))
  const isFiles = isOsFileDrag(e)
  if (!isOurs && !isFiles) return
  e.preventDefault()
  e.stopPropagation()
  const dest = drag.resolveDestDir(props.item)
  if (isOurs) {
    if (!drag.canDropTo(dest)) {
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'none'
      drag.setDropHover(null, null)
      return
    }
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
    drag.setDropHover(props.item.path, dest)
    return
  }
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  drag.setDropHover(props.item.path, dest, { external: true })
}

function onDragLeave(e: DragEvent) {
  if (!drag) return
  const related = e.relatedTarget as Node | null
  if (related && (e.currentTarget as Node).contains(related)) return
  if (drag.dropHoverPath.value === props.item.path) drag.setDropHover(null, null)
}

function onDrop(e: DragEvent) {
  if (!drag) return
  const types = e.dataTransfer?.types
  const isOurs = !!drag.dragSrc.value || (types != null && [...types].includes(FS_DRAG_MIME))
  if (!isOurs && isOsFileDrag(e)) {
    e.preventDefault()
    e.stopPropagation()
    const dest = drag.resolveDestDir(props.item)
    void drag.dropDataTransfer(dest, e.dataTransfer)
    return
  }
  if (!isOurs) return
  e.preventDefault()
  e.stopPropagation()
  const dest = drag.resolveDestDir(props.item)
  void drag.dropTo(dest)
}
</script>

<template>
  <div class="node">
    <button
      type="button"
      class="row"
      :data-explorer-path="item.path"
      :class="{
        active: store.activePath === item.path,
        cut: isCut || isDragging,
        'drop-target': isDropTarget,
      }"
      :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
      :draggable="!isRenaming"
      :aria-grabbed="isCut || isDragging ? 'true' : undefined"
      @click="onRowClick"
      @contextmenu="emit('context', $event, item)"
      @dragstart="onDragStart"
      @dragend="onDragEnd"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
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
        v-if="mark.show && mark.letter"
        class="tree-letter"
        :class="mark.kind ? `tree-letter--${mark.kind}` : undefined"
        :title="mark.title"
        :aria-label="mark.title"
      >{{ mark.letter }}</span>
      <span
        v-else-if="mark.show"
        class="tree-dot"
        :class="mark.kind ? `tree-dot--${mark.kind}` : undefined"
        :title="mark.title"
        :aria-label="mark.title"
      />
    </button>
    <template v-if="item.is_dir && store.isExpanded(item.path)">
      <ExplorerCreateRow
        v-if="creating && creating.dir === item.path"
        :key="creating.id"
        :kind="creating.kind"
        :depth="depth + 1"
        :dir="item.path"
        :model-value="creating.value"
        @update:model-value="(v) => emit('update:creating', v)"
        @commit="emit('commit-create')"
        @cancel="emit('cancel-create')"
      />
      <ExplorerTreeNode
        v-for="child in store.childrenOf(item.path)"
        :key="child.path"
        :item="child"
        :depth="depth + 1"
        :renaming-path="renamingPath"
        :creating="creating"
        @context="(e, it) => emit('context', e, it)"
        @select="(it) => emit('select', it)"
        @start-rename="(p) => emit('start-rename', p)"
        @commit-rename="(from, name) => emit('commit-rename', from, name)"
        @cancel-rename="emit('cancel-rename')"
        @update:creating="(v) => emit('update:creating', v)"
        @commit-create="emit('commit-create')"
        @cancel-create="emit('cancel-create')"
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
.row.cut {
  opacity: 0.42;
  color: var(--text-muted);
}
.row.cut.active {
  opacity: 0.55;
  color: color-mix(in srgb, var(--primary) 70%, var(--text-muted));
}
.row.cut :deep(.file-tree-icon),
.row.cut .twist {
  opacity: 0.85;
}
.row.drop-target {
  background: color-mix(in srgb, var(--primary) 16%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 45%, transparent);
}
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
.tree-letter {
  margin-left: auto;
  flex-shrink: 0;
  min-width: 14px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.02em;
  font-family: var(--mono);
  text-align: right;
  color: var(--text-muted);
}
.tree-letter--modified {
  color: var(--traj-tool);
}
.tree-letter--added {
  color: var(--traj-context);
}
.tree-letter--deleted,
.tree-letter--conflict {
  color: var(--danger);
}
.tree-dot {
  width: 6px;
  height: 6px;
  margin-left: auto;
  border-radius: 99px;
  background: var(--text-muted);
  flex-shrink: 0;
  box-shadow: 0 0 0 2px color-mix(in srgb, currentColor 18%, transparent);
}
.tree-dot--untracked,
.tree-dot--added {
  background: var(--traj-context);
  color: var(--traj-context);
}
.tree-dot--modified {
  background: var(--traj-tool);
  color: var(--traj-tool);
}
.tree-dot--deleted,
.tree-dot--conflict {
  background: var(--danger);
  color: var(--danger);
}
.tree-dot--changed {
  background: var(--text-muted);
  color: var(--text-muted);
}
</style>
