export type GitMarkKind = 'untracked' | 'added' | 'deleted' | 'modified' | 'changed' | 'conflict'

export type GitPathMark = {
  kind: GitMarkKind
  code: string
}

/** Map porcelain code (e.g. " M", "??") to a stable mark kind. */
export function gitMarkKind(code: string): GitMarkKind {
  if (code.includes('U')) return 'conflict'
  if (code.includes('?')) return 'untracked'
  if (code.includes('D')) return 'deleted'
  if (code.includes('A')) return 'added'
  if (code.includes('M')) return 'modified'
  return 'changed'
}

/** Human-readable label aligned with Git panel. */
export function gitMarkLabel(code: string): string {
  if (code.includes('?')) return '未跟踪'
  if (code.includes('D')) return '删除'
  if (code.includes('A')) return '新增'
  if (code.includes('M')) return '修改'
  if (code.includes('U')) return '冲突'
  return code.trim() || '改动'
}

export function gitMarkTitle(mark: GitPathMark, path?: string): string {
  const label = gitMarkLabel(mark.code)
  return path ? `${label} · ${path}` : label
}
