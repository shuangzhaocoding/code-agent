<script setup lang="ts">
import AppIcon from '@/components/AppIcon.vue'
import type { FolderTreeNode } from '@/utils/sshHostGroups'

defineOptions({ name: 'WorkspaceFolderNode' })

const props = defineProps<{
  node: FolderTreeNode
  open: boolean
  dropOver: boolean
  dragging: boolean
  hostCount: number
  childOpen: (path: string) => boolean
  childDropOver: (path: string) => boolean
  childDragging: (path: string) => boolean
  hostCountOf: (path: string) => number
}>()

const emit = defineEmits<{
  toggle: [path: string]
  contextmenu: [path: string, e: MouseEvent]
  dragstart: [path: string, e: DragEvent]
  dragend: []
  dragover: [path: string, e: DragEvent]
  dragleave: [path: string, e: DragEvent]
  drop: [path: string, e: DragEvent]
}>()

defineSlots<{
  default(props: { folderPath: string }): unknown
}>()
</script>

<template>
  <div
    class="folder-node"
    :class="{ open: props.open, 'drop-over': props.dropOver, dragging: props.dragging }"
    @dragover="emit('dragover', node.path, $event)"
    @dragleave="emit('dragleave', node.path, $event)"
    @drop="emit('drop', node.path, $event)"
  >
    <div
      class="folder-row"
      draggable="true"
      @click="emit('toggle', node.path)"
      @contextmenu.prevent.stop="emit('contextmenu', node.path, $event)"
      @dragstart.stop="emit('dragstart', node.path, $event)"
      @dragend="emit('dragend')"
    >
      <AppIcon
        class="folder-chev"
        :name="props.open ? 'chevron-down' : 'chevron-right'"
        :size="11"
        :stroke-width="2"
      />
      <AppIcon class="folder-icon" name="folder" :size="13" :stroke-width="1.75" />
      <span class="folder-label" :title="node.path">{{ node.name }}</span>
      <span class="folder-count">{{ props.hostCount }}</span>
    </div>

    <div v-if="props.open" class="folder-body">
      <WorkspaceFolderNode
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :open="childOpen(child.path)"
        :drop-over="childDropOver(child.path)"
        :dragging="childDragging(child.path)"
        :host-count="hostCountOf(child.path)"
        :child-open="childOpen"
        :child-drop-over="childDropOver"
        :child-dragging="childDragging"
        :host-count-of="hostCountOf"
        @toggle="emit('toggle', $event)"
        @contextmenu="(p, e) => emit('contextmenu', p, e)"
        @dragstart="(p, e) => emit('dragstart', p, e)"
        @dragend="emit('dragend')"
        @dragover="(p, e) => emit('dragover', p, e)"
        @dragleave="(p, e) => emit('dragleave', p, e)"
        @drop="(p, e) => emit('drop', p, e)"
      >
        <template #default="{ folderPath }">
          <slot :folder-path="folderPath" />
        </template>
      </WorkspaceFolderNode>

      <slot :folder-path="node.path" />
    </div>
  </div>
</template>

<style scoped>
.folder-node {
  margin: 0 0 4px;
  border-radius: 8px;
  transition: background 0.12s ease, box-shadow 0.12s ease;
}

.folder-node.drop-over {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 40%, transparent);
}

.folder-node.dragging > .folder-row {
  opacity: 0.45;
}

.folder-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  margin: 0 2px;
  padding: 3px 8px 3px 6px;
  border-radius: 8px;
  color: var(--text-h);
  cursor: grab;
  user-select: none;
}

.folder-row:active {
  cursor: grabbing;
}

.folder-row:hover {
  background: color-mix(in srgb, var(--text-h) 5%, transparent);
}

.folder-chev,
.folder-icon {
  flex-shrink: 0;
  color: var(--text-muted);
}

.folder-label {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 650;
}

.folder-count {
  flex-shrink: 0;
  min-width: 16px;
  text-align: right;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
}

.folder-body {
  margin: 2px 0 4px 12px;
  padding-left: 6px;
  border-left: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
}
</style>
