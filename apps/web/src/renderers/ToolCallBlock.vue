<script setup lang="ts">
import { computed } from 'vue'
import type { Block } from '@/protocol/applyEvent'
import EventCard from '@/components/EventCard.vue'
import { useAppStore } from '@/stores/app'

const props = defineProps<{ block: Block }>()
const store = useAppStore()

type Tone = 'default' | 'think' | 'danger' | 'tool'

const catalog: Record<string, { icon: string; label: string; tone: Tone }> = {
  git_status: { icon: 'git', label: 'Git 状态', tone: 'default' },
  git_diff: { icon: 'git', label: 'Git Diff', tone: 'default' },
  git_log: { icon: 'git', label: 'Git 日志', tone: 'default' },
  git_branch: { icon: 'git', label: 'Git 分支', tone: 'default' },
  git_add: { icon: 'git', label: 'Git 暂存', tone: 'tool' },
  git_commit: { icon: 'git', label: 'Git 提交', tone: 'tool' },
  git_push: { icon: 'git', label: 'Git 推送', tone: 'danger' },
  git_pull: { icon: 'git', label: 'Git 拉取', tone: 'tool' },
  git_checkout: { icon: 'git', label: 'Git 切换', tone: 'danger' },
  git_reset: { icon: 'git', label: 'Git Reset', tone: 'danger' },
  write_file: { icon: 'file-plus', label: '写入文件', tone: 'tool' },
  search_replace: { icon: 'file-edit', label: '编辑文件', tone: 'tool' },
  delete_file: { icon: 'trash', label: '删除文件', tone: 'danger' },
  read_file: { icon: 'eye', label: '读取文件', tone: 'default' },
  list_dir: { icon: 'folder', label: '列出目录', tone: 'default' },
  glob_search: { icon: 'search', label: '查找文件', tone: 'default' },
  grep_search: { icon: 'search', label: '搜索内容', tone: 'default' },
  run_command: { icon: 'terminal', label: '运行命令', tone: 'default' },
  load_skill: { icon: 'book', label: '加载 Skill', tone: 'tool' },
  list_skills: { icon: 'puzzle', label: '列出 Skill', tone: 'default' },
  'file.read': { icon: 'eye', label: '读取文件', tone: 'default' },
  'skill.activated': { icon: 'book', label: '加载 Skill', tone: 'tool' },
  'tool.call': { icon: 'wrench', label: '工具调用', tone: 'tool' },
  'tool.result': { icon: 'check', label: '工具结果', tone: 'tool' },
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed
    } catch {
      return null
    }
  }
  return null
}

const args = computed(() => asRecord(props.block.meta.args) || {})

const toolName = computed(() => String(props.block.meta.name || props.block.type || 'tool'))

const spec = computed(() => {
  const name = toolName.value
  const type = props.block.type
  return (
    catalog[name] ||
    catalog[type] || {
      icon: type === 'tool.result' ? 'check' : 'wrench',
      label: type === 'tool.result' ? '工具结果' : name,
      tone: 'tool' as Tone,
    }
  )
})

const path = computed(() =>
  String(props.block.meta.path || args.value.path || args.value.name || props.block.meta.name || ''),
)

const fileOp = computed(() =>
  ['write_file', 'search_replace', 'delete_file', 'read_file', 'file.read'].includes(toolName.value) ||
  ['file.read', 'file.diff', 'file.delete'].includes(props.block.type),
)

function openFile() {
  if (fileOp.value && path.value) store.openAgentFile(path.value)
}

const subtitle = computed(() => {
  if (toolName.value === 'run_command' || props.block.type === 'terminal') {
    return String(args.value.command || props.block.meta.command || '')
  }
  if (props.block.type === 'skill.activated') return String(props.block.meta.name || '')
  return path.value && path.value !== spec.value.label ? path.value : ''
})

const title = computed(() => spec.value.label)

const body = computed(() => {
  if (props.block.text) return props.block.text
  const copy = { ...args.value }
  for (const key of ['content', 'old_string', 'new_string']) {
    const val = copy[key]
    if (typeof val === 'string' && val.length > 240) copy[key] = `${val.slice(0, 240)}…`
  }
  if (Object.keys(copy).length) return JSON.stringify(copy, null, 2)
  const meta = { ...props.block.meta }
  delete meta.args
  return Object.keys(meta).length ? JSON.stringify(meta, null, 2) : ''
})
</script>

<template>
  <EventCard
    :icon="spec.icon"
    :title="title"
    :subtitle="subtitle"
    :tone="spec.tone"
    :status="block.status"
    :default-open="block.status === 'error'"
    :activatable="fileOp && !!path"
    @activate="openFile"
  >
    <pre class="payload">{{ body || '（无详情）' }}</pre>
  </EventCard>
</template>

<style scoped>
.payload {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  max-height: 260px;
  overflow: auto;
}
</style>
