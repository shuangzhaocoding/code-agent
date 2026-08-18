<script setup lang="ts">
import { computed } from 'vue'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'
import { useAppStore } from '@/stores/app'

const props = defineProps<{ block: Block }>()
const store = useAppStore()

const action = computed(() => String(props.block.meta.action || (props.block.type === 'file.delete' ? 'delete' : props.block.type === 'file.write' ? 'create' : 'edit')))

const title = computed(() => {
  if (action.value === 'delete') return '删除文件'
  if (action.value === 'create') return '新增文件'
  if (action.value === 'overwrite') return '写入文件'
  return '编辑文件'
})

const icon = computed(() => {
  if (action.value === 'delete') return 'trash'
  if (action.value === 'create') return 'file-plus'
  return 'file-edit'
})

const tone = computed(() => (action.value === 'delete' ? 'danger' : 'tool'))

const path = computed(() => String(props.block.meta.path || ''))

const lines = computed(() => (props.block.text || '').split('\n'))

const stats = computed(() => {
  const added = lines.value.filter((l) => l.startsWith('+') && !l.startsWith('+++')).length
  const removed = lines.value.filter((l) => l.startsWith('-') && !l.startsWith('---')).length
  return { added, removed }
})

function openFile() {
  if (path.value) store.openAgentFile(path.value)
}
</script>

<template>
  <EventCard
    :icon="icon"
    :title="title"
    :subtitle="path"
    :tone="tone"
    :status="block.status"
    :default-open="false"
    :activatable="!!path"
    @activate="openFile"
  >
    <div v-if="action !== 'delete' && (stats.added || stats.removed)" class="stats">
      <span class="add">+{{ stats.added }}</span>
      <span class="del">-{{ stats.removed }}</span>
    </div>
    <pre v-if="block.text" class="diff"><span
      v-for="(line, i) in lines"
      :key="i"
      :class="{
        add: line.startsWith('+') && !line.startsWith('+++'),
        del: line.startsWith('-') && !line.startsWith('---'),
        hunk: line.startsWith('@@'),
      }"
    >{{ line }}{{ i < lines.length - 1 ? '\n' : '' }}</span></pre>
    <p v-else class="empty">{{ action === 'delete' ? '已删除该路径' : '无变更内容' }}</p>
  </EventCard>
</template>

<style scoped>
.stats {
  display: flex;
  gap: 10px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 8px;
}
.add { color: var(--ok); }
.del { color: var(--danger); }
.diff {
  margin: 0;
  font-family: var(--mono);
  font-size: 11.5px;
  line-height: 1.45;
  overflow: auto;
  max-height: 320px;
  white-space: pre;
}
.diff .add { color: var(--ok); background: color-mix(in srgb, var(--ok) 10%, transparent); }
.diff .del { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); }
.diff .hunk { color: var(--primary); }
.empty {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
