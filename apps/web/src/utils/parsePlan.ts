export type PlanStep = {
  index: number
  title: string
  detail: string
}

const ITEM_RE = /^(\d+)[.)、]\s+(.*)$/
const PLAN_HEADING_RE = /^(#{1,3}\s*)?(计划|任务步骤|实施步骤|实施计划|步骤|Plan|Task plan|Steps)\b/i

function splitTitle(body: string): { title: string; detail: string } {
  const trimmed = body.trim()
  const boldSep = trimmed.match(/^\*\*(.+?)\*\*\s*[—–\-：:]\s*(.*)$/s)
  if (boldSep) return { title: boldSep[1].trim(), detail: boldSep[2].trim() }
  const boldTail = trimmed.match(/^\*\*(.+?)\*\*\s*(.*)$/s)
  if (boldTail && boldTail[2].trim()) return { title: boldTail[1].trim(), detail: boldTail[2].trim() }
  const colon = trimmed.match(/^(.{2,48}?)[：:]\s+(.+)$/s)
  if (colon) return { title: colon[1].replace(/\*\*/g, '').trim(), detail: colon[2].trim() }
  return { title: trimmed.replace(/\*\*/g, ''), detail: '' }
}

export function extractPlanSteps(markdown: string): { before: string; steps: PlanStep[]; after: string } | null {
  const lines = (markdown || '').split('\n')
  let start = -1
  for (let i = 0; i < lines.length; i++) {
    if (ITEM_RE.test(lines[i].trim())) {
      start = i
      break
    }
  }
  if (start < 0) return null

  const headingAt = start > 0 && PLAN_HEADING_RE.test(lines[start - 1].trim()) ? start - 1 : start
  const steps: PlanStep[] = []
  let i = start
  let current: { index: number; chunks: string[] } | null = null

  const flush = () => {
    if (!current) return
    const body = current.chunks.join('\n').trim()
    if (!body) return
    const parts = splitTitle(body)
    steps.push({ index: current.index, title: parts.title, detail: parts.detail })
  }

  while (i < lines.length) {
    const raw = lines[i]
    const trimmed = raw.trim()
    const item = trimmed.match(ITEM_RE)
    if (item) {
      flush()
      current = { index: Number(item[1]), chunks: [item[2] || ''] }
      i += 1
      continue
    }
    if (!current) break
    if (!trimmed) {
      const next = lines.slice(i + 1).find((line) => line.trim())
      if (next && (ITEM_RE.test(next.trim()) || PLAN_HEADING_RE.test(next.trim()) || next.trim().startsWith('#'))) {
        break
      }
      current.chunks.push('')
      i += 1
      continue
    }
    if (trimmed.startsWith('#') || trimmed.startsWith('---')) break
    current.chunks.push(raw.replace(/^\s{2,}/, ''))
    i += 1
  }
  flush()
  if (steps.length < 2) return null

  const before = lines.slice(0, headingAt).join('\n').trim()
  const after = lines.slice(i).join('\n').trim()
  return { before, steps, after }
}
