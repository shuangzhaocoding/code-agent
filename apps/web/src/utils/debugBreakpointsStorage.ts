import { normalizeDebugPath } from '@/utils/debugPath'

export type StoredBreakpoint = {
  line: number
  condition?: string
  hitCondition?: string
  logMessage?: string
}

export const BREAKPOINTS_FILE_REL = '.code-agent/breakpoints.json'

const LS_PREFIX = 'ca.debug.breakpoints.'

export function breakpointsLocalKey(workspaceId: string) {
  return `${LS_PREFIX}${workspaceId}`
}

export function normalizeBreakpointList(raw: unknown): StoredBreakpoint[] {
  if (!Array.isArray(raw)) return []
  const seen = new Set<number>()
  const out: StoredBreakpoint[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const line = Math.floor(Number((item as StoredBreakpoint).line))
    if (!Number.isFinite(line) || line < 1 || seen.has(line)) continue
    seen.add(line)
    const bp: StoredBreakpoint = { line }
    const condition = (item as StoredBreakpoint).condition
    const hitCondition = (item as StoredBreakpoint).hitCondition
    const logMessage = (item as StoredBreakpoint).logMessage
    if (typeof condition === 'string' && condition.trim()) bp.condition = condition.trim()
    if (typeof hitCondition === 'string' && hitCondition.trim()) bp.hitCondition = hitCondition.trim()
    if (typeof logMessage === 'string' && logMessage.trim()) bp.logMessage = logMessage.trim()
    out.push(bp)
  }
  return out.sort((a, b) => a.line - b.line)
}

export function pruneBreakpointsMap(
  map: Record<string, StoredBreakpoint[]>,
  workspaceRoot?: string | null,
): Record<string, StoredBreakpoint[]> {
  const out: Record<string, StoredBreakpoint[]> = {}
  for (const [path, list] of Object.entries(map)) {
    const key = normalizeDebugPath(path, workspaceRoot) || path.replace(/\\/g, '/')
    if (!key) continue
    const cleaned = normalizeBreakpointList(list)
    if (!cleaned.length) continue
    const prev = out[key] || []
    const merged = normalizeBreakpointList([...prev, ...cleaned])
    if (merged.length) out[key] = merged
  }
  return out
}

export function readBreakpointsLocal(workspaceId: string | null | undefined) {
  if (!workspaceId || typeof localStorage === 'undefined') return {}
  try {
    const raw = localStorage.getItem(breakpointsLocalKey(workspaceId))
    if (!raw) return {}
    return pruneBreakpointsMap(JSON.parse(raw) as Record<string, StoredBreakpoint[]>)
  } catch {
    return {}
  }
}

export function writeBreakpointsLocal(
  workspaceId: string | null | undefined,
  map: Record<string, StoredBreakpoint[]>,
) {
  if (!workspaceId || typeof localStorage === 'undefined') return
  try {
    const cleaned = pruneBreakpointsMap(map)
    const key = breakpointsLocalKey(workspaceId)
    if (!Object.keys(cleaned).length) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(cleaned))
  } catch {
    /* quota / private mode */
  }
}

export function parseBreakpointsFile(raw: string): Record<string, StoredBreakpoint[]> {
  try {
    const data = JSON.parse(raw) as unknown
    if (!data || typeof data !== 'object') return {}
    const map =
      'breakpoints' in (data as Record<string, unknown>) &&
      typeof (data as { breakpoints?: unknown }).breakpoints === 'object' &&
      (data as { breakpoints?: unknown }).breakpoints
        ? ((data as { breakpoints: Record<string, StoredBreakpoint[]> }).breakpoints)
        : (data as Record<string, StoredBreakpoint[]>)
    return pruneBreakpointsMap(map)
  } catch {
    return {}
  }
}

export function serializeBreakpointsFile(map: Record<string, StoredBreakpoint[]>) {
  return `${JSON.stringify({ version: 1, breakpoints: pruneBreakpointsMap(map) }, null, 2)}\n`
}
