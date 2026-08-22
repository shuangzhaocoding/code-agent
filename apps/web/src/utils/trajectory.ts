import type { Block, ChatMessage } from '@/protocol/applyEvent'

export type TrajectoryKind = 'user' | 'assistant' | 'think' | 'tool' | 'context' | 'terminal' | 'diff' | 'error' | 'other'

export type TrajectoryEntry = {
  id: string
  turn: number
  kind: TrajectoryKind
  label: string
  subtitle: string
  block: Block
  msgId: string
  msgRole: string
}

export type TimelineSpan = {
  id: string
  entryId: string
  kind: TrajectoryKind
  label: string
  turn: number
  start: number
  end: number
  left: number
  width: number
  streaming: boolean
}

const CONVERSATION_TYPES = new Set(['user.text', 'assistant.markdown', 'approval'])

const READ_TOOLS = new Set([
  'read_file',
  'list_dir',
  'glob_search',
  'grep_search',
  'git_status',
  'git_diff',
  'git_log',
  'git_branch',
  'list_skills',
  'file.read',
])

export function isConversationBlock(type: string): boolean {
  return CONVERSATION_TYPES.has(type)
}

export function classifyBlock(block: Block): TrajectoryKind {
  if (block.type === 'user.text') return 'user'
  if (block.type === 'assistant.markdown') return 'assistant'
  if (block.type === 'assistant.thinking') return 'think'
  if (block.type === 'error') return 'error'
  if (block.type === 'terminal') return 'terminal'
  if (block.type === 'file.diff' || block.type.startsWith('file.')) return 'diff'
  if (block.type === 'tool.call' || block.type === 'tool.result') return 'tool'

  const name = String(block.meta.name || block.type || '')
  if (READ_TOOLS.has(name)) return 'context'
  if (['write_file', 'search_replace', 'delete_file', 'run_command', 'load_skill', 'skill.activated'].includes(name)) {
    return name === 'run_command' ? 'terminal' : 'tool'
  }
  if (['git_add', 'git_commit', 'git_push', 'git_pull', 'git_checkout', 'git_reset'].includes(name)) return 'tool'
  return 'other'
}

function blockSubtitle(block: Block): string {
  const args = (block.meta.args as Record<string, unknown>) || {}
  const name = String(block.meta.name || '')
  if (name === 'run_command' || block.type === 'terminal') {
    return String(args.command || block.meta.command || '')
  }
  const path = String(block.meta.path || args.path || args.name || '')
  if (path) return path
  // Avoid coupling ledger subtitle to growing stream text (major re-render cost).
  if (block.status === 'streaming') {
    if (block.type === 'assistant.thinking') return '思考中…'
    if (block.type === 'tool.call' || block.type === 'tool.result') return '执行中…'
    return '进行中…'
  }
  if (block.text) {
    const oneLine = block.text.trim().split('\n')[0]
    return oneLine.length > 72 ? `${oneLine.slice(0, 72)}…` : oneLine
  }
  return block.type
}

function blockLabel(block: Block, kind: TrajectoryKind): string {
  const name = String(block.meta.name || '')
  const labels: Record<string, string> = {
    'assistant.thinking': '思考',
    'assistant.markdown': '回复',
    'user.text': '用户',
    'tool.call': '工具调用',
    'tool.result': '工具结果',
    'file.diff': '文件变更',
    'file.write': '写入文件',
    'file.delete': '删除文件',
    'file.read': '读取文件',
    terminal: '终端',
    error: '错误',
    approval: '审批',
    'skill.activated': 'Skill',
  }
  if (labels[block.type]) return labels[block.type]
  if (name) {
    const toolLabels: Record<string, string> = {
      run_command: '运行命令',
      read_file: '读取文件',
      write_file: '写入文件',
      search_replace: '编辑文件',
      delete_file: '删除文件',
      list_dir: '列出目录',
      glob_search: '查找文件',
      grep_search: '搜索内容',
      load_skill: '加载 Skill',
    }
    if (toolLabels[name]) return toolLabels[name]
    return name
  }
  if (kind === 'think') return '思考'
  if (kind === 'context') return '上下文'
  if (kind === 'diff') return '文件变更'
  if (kind === 'tool') return '工具'
  return block.type
}

function toMs(value: number | string | undefined, fallback: number): number {
  if (value === undefined || value === null || value === '') return fallback
  if (typeof value === 'number') return value
  const ms = new Date(value).getTime()
  return Number.isFinite(ms) ? ms : fallback
}

export function buildTrajectory(messages: ChatMessage[], opts?: { snapshot?: boolean }): TrajectoryEntry[] {
  const entries: TrajectoryEntry[] = []
  let turn = 0
  const snapshot = opts?.snapshot === true

  for (const msg of messages) {
    if (msg.role === 'user') turn += 1
    const effectiveTurn = turn || 1

    for (const block of msg.blocks) {
      const kind = classifyBlock(block)
      const blockView = snapshot
        ? ({
            ...block,
            meta: { ...(block.meta || {}) },
          } as Block)
        : block
      entries.push({
        id: `${msg.id}:${block.id}`,
        turn: effectiveTurn,
        kind,
        label: blockLabel(blockView, kind),
        subtitle: blockSubtitle(blockView),
        block: blockView,
        msgId: msg.id,
        msgRole: msg.role,
      })
    }
  }

  return entries
}

export function trajectoryEntriesForLedger(messages: ChatMessage[]): TrajectoryEntry[] {
  return buildTrajectory(messages, { snapshot: true }).filter((entry) => !isConversationBlock(entry.block.type))
}

export function buildTimelineSpans(entries: TrajectoryEntry[]): TimelineSpan[] {
  if (!entries.length) return []

  const now = Date.now()
  const timed = entries.map((entry, index) => {
    const base = now - (entries.length - index) * 1200
    const start = toMs(entry.block.started_at, base)
    let end = toMs(entry.block.ended_at, 0)
    if (!end || end <= start) {
      // Streaming: keep a stable short bar instead of extending every paint with Date.now()
      end = entry.block.status === 'streaming' ? start + 900 : start + 600
    }
    return { entry, start, end }
  })

  const min = timed[0].start
  const max = Math.max(...timed.map((t) => t.end), min + 1)
  const range = max - min || 1

  return timed.map(({ entry, start, end }) => ({
    id: entry.id,
    entryId: entry.id,
    kind: entry.kind,
    label: entry.label,
    turn: entry.turn,
    start,
    end,
    left: ((start - min) / range) * 100,
    width: Math.max(((end - start) / range) * 100, 1.2),
    streaming: entry.block.status === 'streaming',
  }))
}

export const TRAJECTORY_FILTERS: { id: 'all' | TrajectoryKind; label: string }[] = [
  { id: 'all', label: '全部' },
  { id: 'tool', label: '工具' },
  { id: 'think', label: '思考' },
  { id: 'context', label: '上下文' },
  { id: 'diff', label: '变更' },
  { id: 'terminal', label: '终端' },
  { id: 'error', label: '错误' },
]
