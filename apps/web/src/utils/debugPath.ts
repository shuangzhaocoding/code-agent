/** Normalize workspace / absolute paths for debug UI comparisons. */
export function normalizeDebugPath(path: string | null | undefined, workspaceRoot?: string | null): string {
  if (!path) return ''
  let p = path.replace(/\\/g, '/').trim()
  const root = (workspaceRoot || '').replace(/\\/g, '/').replace(/\/+$/, '')
  if (root) {
    if (p === root) return ''
    const prefix = `${root}/`
    if (p.startsWith(prefix)) p = p.slice(prefix.length)
  }
  if (p.startsWith('/')) {
    const parts = p.split('/').filter(Boolean)
    return parts.join('/')
  }
  return p.replace(/^\/+/, '')
}

export function debugPathsEqual(
  a: string | null | undefined,
  b: string | null | undefined,
  workspaceRoot?: string | null,
): boolean {
  const na = normalizeDebugPath(a, workspaceRoot)
  const nb = normalizeDebugPath(b, workspaceRoot)
  if (!na || !nb) return false
  return na === nb
}
