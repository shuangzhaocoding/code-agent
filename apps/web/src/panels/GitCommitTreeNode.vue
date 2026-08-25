<script setup lang="ts">
import GitCommitTreeNode from '@/panels/GitCommitTreeNode.vue'
import FileTreeIcon from '@/components/FileTreeIcon.vue'
import type { GitTreeItem } from '@/utils/gitFileTree'

defineOptions({ name: 'GitCommitTreeNode' })

defineProps<{
  node: GitTreeItem
  depth: number
  expanded: Set<string>
  activePath: string
  selectable?: boolean
  selected?: Set<string>
}>()

const emit = defineEmits<{
  toggle: [path: string]
  select: [path: string]
  open: [path: string]
  check: [path: string]
  context: [event: MouseEvent, path: string, kind: 'file' | 'dir']
}>()
</script>

<template>
  <div class="node">
    <button
      v-if="node.kind === 'dir'"
      type="button"
      class="row dir"
      :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
      @click="emit('toggle', node.path)"
      @contextmenu.prevent.stop="emit('context', $event, node.path, 'dir')"
    >
      <span class="twist" :class="{ on: expanded.has(node.path) }" />
      <FileTreeIcon kind="dir" :path="node.path" :expanded="expanded.has(node.path)" :size="16" />
      <span class="label">{{ node.name }}</span>
      <span class="stats">
        <em v-if="node.additions" class="add">+{{ node.additions }}</em>
        <em v-if="node.deletions" class="del">-{{ node.deletions }}</em>
      </span>
    </button>
    <div
      v-else
      class="row file"
      :class="{ on: activePath === node.path }"
      :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
      @contextmenu.prevent.stop="emit('context', $event, node.path, 'file')"
    >
      <span class="twist hidden" />
      <input
        v-if="selectable"
        type="checkbox"
        class="check"
        :checked="selected?.has(node.path)"
        @click.stop
        @change="emit('check', node.path)"
      />
      <button
        type="button"
        class="row-main"
        :title="node.path"
        @click="emit('select', node.path)"
        @dblclick="emit('open', node.path)"
      >
        <FileTreeIcon kind="file" :path="node.path" :size="16" />
        <span class="code">{{ node.status }}</span>
        <span class="label">{{ node.name }}</span>
        <span class="stats">
          <em v-if="node.additions" class="add">+{{ node.additions }}</em>
          <em v-if="node.deletions" class="del">-{{ node.deletions }}</em>
        </span>
      </button>
    </div>
    <template v-if="node.kind === 'dir' && expanded.has(node.path)">
      <GitCommitTreeNode
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :depth="depth + 1"
        :expanded="expanded"
        :active-path="activePath"
        :selectable="selectable"
        :selected="selected"
        @toggle="(p) => emit('toggle', p)"
        @select="(p) => emit('select', p)"
        @open="(p) => emit('open', p)"
        @check="(p) => emit('check', p)"
        @context="(e, p, k) => emit('context', e, p, k)"
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
  text-align: left;
  padding-right: 8px;
  font-size: 12px;
}
.row:hover { background: var(--bg-muted); }
.row.on { background: var(--primary-soft); }
.row-main {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
  height: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
  font-size: inherit;
  padding: 0;
}
.twist {
  width: 8px;
  height: 8px;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: rotate(-45deg);
  opacity: 0.55;
  flex-shrink: 0;
}
.twist.on { transform: rotate(45deg); }
.twist.hidden { visibility: hidden; }
.check {
  width: 13px;
  height: 13px;
  margin: 0;
  flex-shrink: 0;
  accent-color: var(--primary);
}
.code {
  font-family: var(--mono);
  min-width: 1.25em;
  color: var(--primary);
  flex-shrink: 0;
}
.label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.stats {
  display: inline-flex;
  gap: 6px;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
}
.stats em { font-style: normal; }
.add { color: #059669; }
.del { color: var(--error-text); }
</style>
