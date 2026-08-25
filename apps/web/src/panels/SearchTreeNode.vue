<script setup lang="ts">
import SearchTreeNode from '@/panels/SearchTreeNode.vue'
import FileTreeIcon from '@/components/FileTreeIcon.vue'

defineOptions({ name: 'SearchTreeNode' })

export type SearchHit = { path: string; line: number; text: string }
export type SearchTreeItem = {
  name: string
  path: string
  kind: 'dir' | 'file'
  count: number
  items?: SearchHit[]
  children?: SearchTreeItem[]
}

defineProps<{
  node: SearchTreeItem
  depth: number
  expanded: Set<string>
  query: string
  caseSensitive: boolean
  activePath: string | null
  activeLine: number | null
}>()

const emit = defineEmits<{
  toggle: [path: string]
  open: [hit: SearchHit]
}>()

function snippetParts(text: string, q: string, caseSensitive: boolean) {
  if (!q) return [{ t: text, mark: false }]
  const hay = caseSensitive ? text : text.toLowerCase()
  const needle = caseSensitive ? q : q.toLowerCase()
  const i = hay.indexOf(needle)
  if (i < 0) return [{ t: text, mark: false }]
  return [
    { t: text.slice(0, i), mark: false },
    { t: text.slice(i, i + q.length), mark: true },
    { t: text.slice(i + q.length), mark: false },
  ]
}
</script>

<template>
  <div class="node">
    <button
      v-if="node.kind === 'dir'"
      type="button"
      class="row dir"
      :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
      @click="emit('toggle', node.path)"
    >
      <span class="twist" :class="{ on: expanded.has(node.path) }" />
      <FileTreeIcon kind="dir" :path="node.path" :expanded="expanded.has(node.path)" :size="16" />
      <span class="label">{{ node.name }}</span>
      <span class="count">{{ node.count }}</span>
    </button>
    <template v-else>
      <button
        type="button"
        class="row file"
        :class="{ active: activePath === node.path }"
        :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
        :title="node.path"
        @click="node.items?.[0] && emit('open', node.items[0])"
      >
        <span class="twist hidden" />
        <FileTreeIcon kind="file" :path="node.path" :size="16" />
        <span class="label">{{ node.name }}</span>
        <span class="count">{{ node.count }}</span>
      </button>
      <button
        v-for="hit in node.items"
        :key="`${hit.path}:${hit.line}`"
        type="button"
        class="line"
        :class="{ active: activePath === hit.path && activeLine === hit.line }"
        :style="{ paddingLeft: 8 + (depth + 1) * 14 + 18 + 'px' }"
        @click="emit('open', hit)"
      >
        <span class="no">{{ hit.line }}</span>
        <span class="text">
          <template v-for="(part, i) in snippetParts(hit.text, query, caseSensitive)" :key="i">
            <mark v-if="part.mark">{{ part.t }}</mark>
            <template v-else>{{ part.t }}</template>
          </template>
        </span>
      </button>
    </template>
    <template v-if="node.kind === 'dir' && expanded.has(node.path)">
      <SearchTreeNode
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :depth="depth + 1"
        :expanded="expanded"
        :query="query"
        :case-sensitive="caseSensitive"
        :active-path="activePath"
        :active-line="activeLine"
        @toggle="(p) => emit('toggle', p)"
        @open="(hit) => emit('open', hit)"
      />
    </template>
  </div>
</template>

<style scoped>
.row,
.line {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}
.row {
  height: 26px;
  padding-right: 8px;
  font-size: 13px;
}
.row:hover,
.line:hover { background: var(--bg-muted); }
.row.active,
.line.active { background: var(--primary-soft); color: var(--primary); }
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
.label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.count {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
}
.line {
  min-height: 22px;
  padding-top: 3px;
  padding-bottom: 3px;
  padding-right: 12px;
  color: var(--text);
  font-size: 12px;
}
.no {
  flex-shrink: 0;
  width: 28px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-muted);
  text-align: right;
}
.text {
  min-width: 0;
  font-family: var(--mono);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.text mark {
  padding: 0 1px;
  border-radius: 2px;
  background: var(--primary-soft);
  color: var(--text-h);
  font-weight: 600;
}
</style>
