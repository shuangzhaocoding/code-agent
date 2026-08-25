export type GitCommit = {
  hash: string
  short: string
  parents: string[]
  author: string
  email: string
  date: string
  refs: string[]
  subject: string
  is_head?: boolean
}

export type GraphRow = GitCommit & {
  lane: number
  maxLane: number
  through: number[]
  lines: { from: number; to: number }[]
}

const LANE_COLORS = [
  'var(--primary)',
  '#22c55e',
  '#eab308',
  '#f97316',
  '#a855f7',
  '#06b6d4',
  '#ef4444',
  '#ec4899',
]

export function laneColor(lane: number) {
  return LANE_COLORS[((lane % LANE_COLORS.length) + LANE_COLORS.length) % LANE_COLORS.length]
}

export function layoutGitGraph(commits: GitCommit[]): GraphRow[] {
  const pending: (string | null)[] = []
  const rows: GraphRow[] = []

  for (const commit of commits) {
    let lane = pending.indexOf(commit.hash)
    if (lane < 0) {
      lane = pending.indexOf(null)
      if (lane < 0) {
        lane = pending.length
        pending.push(commit.hash)
      } else {
        pending[lane] = commit.hash
      }
    }

    const through = pending.map((hash, index) => (hash ? index : -1)).filter((index) => index >= 0)
    const lines: { from: number; to: number }[] = []
    const parents = commit.parents.filter(Boolean)

    if (!parents.length) {
      pending[lane] = null
    } else {
      const first = parents[0]
      const existing = pending.findIndex((hash, index) => index !== lane && hash === first)
      if (existing >= 0) {
        lines.push({ from: lane, to: existing })
        pending[lane] = null
      } else {
        pending[lane] = first
        lines.push({ from: lane, to: lane })
      }
      for (const parent of parents.slice(1)) {
        if (parent === first) continue
        let to = pending.indexOf(parent)
        if (to < 0) {
          to = pending.findIndex((hash, index) => hash == null && index !== lane)
          if (to < 0) {
            pending.push(parent)
            to = pending.length - 1
          } else {
            pending[to] = parent
          }
        }
        lines.push({ from: lane, to })
      }
    }

    while (pending.length && pending[pending.length - 1] == null) pending.pop()

    rows.push({
      ...commit,
      lane,
      maxLane: Math.max(lane, pending.length - 1, ...through, ...lines.flatMap((line) => [line.from, line.to])),
      through,
      lines,
    })
  }

  const globalMax = rows.reduce((max, row) => Math.max(max, row.maxLane), 0)
  return rows.map((row) => ({ ...row, maxLane: Math.max(0, globalMax) }))
}

export function formatCommitTime(iso: string) {
  const stamp = Date.parse(iso)
  if (Number.isNaN(stamp)) return ''
  const seconds = Math.max(0, Math.round((Date.now() - stamp) / 1000))
  if (seconds < 60) return '刚刚'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)} 天前`
  return new Date(stamp).toLocaleDateString()
}
