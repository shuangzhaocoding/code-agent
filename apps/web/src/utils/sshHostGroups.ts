/** Nested SSH host folders (MobaXterm-style). Paths use `/` as separator. */

export const FOLDER_SEP = '/'
const KEY = 'ca.sshHostGroups'

export type FolderTreeNode = {
  path: string
  name: string
  children: FolderTreeNode[]
}

export function normalizeFolderPath(path: string): string {
  return String(path || '')
    .split(FOLDER_SEP)
    .map((s) => s.trim())
    .filter(Boolean)
    .join(FOLDER_SEP)
}

export function sanitizeFolderName(name: string): string {
  return String(name || '')
    .trim()
    .replace(/[\\/]+/g, '')
    .trim()
}

export function folderLeafName(path: string): string {
  const parts = normalizeFolderPath(path).split(FOLDER_SEP)
  return parts[parts.length - 1] || ''
}

export function parentFolderPath(path: string): string {
  const parts = normalizeFolderPath(path).split(FOLDER_SEP)
  if (parts.length <= 1) return ''
  parts.pop()
  return parts.join(FOLDER_SEP)
}

export function childFolderPath(parent: string, name: string): string {
  const n = sanitizeFolderName(name)
  if (!n) return normalizeFolderPath(parent)
  const p = normalizeFolderPath(parent)
  return p ? `${p}${FOLDER_SEP}${n}` : n
}

export function isUnderFolder(path: string, folder: string): boolean {
  const p = normalizeFolderPath(path)
  const f = normalizeFolderPath(folder)
  if (!f) return Boolean(p)
  return p === f || p.startsWith(`${f}${FOLDER_SEP}`)
}

/** True if `maybeChild` is the same as or nested under `folder`. */
export function isSameOrDescendant(folder: string, maybeChild: string): boolean {
  const f = normalizeFolderPath(folder)
  const c = normalizeFolderPath(maybeChild)
  if (!f || !c) return false
  return c === f || c.startsWith(`${f}${FOLDER_SEP}`)
}

export function rewriteFolderPrefix(path: string, from: string, to: string): string {
  const p = normalizeFolderPath(path)
  const f = normalizeFolderPath(from)
  const t = normalizeFolderPath(to)
  if (!f) return p
  if (p === f) return t
  if (p.startsWith(`${f}${FOLDER_SEP}`)) {
    const rest = p.slice(f.length + 1)
    return t ? `${t}${FOLDER_SEP}${rest}` : rest
  }
  return p
}

export function collectAllFolderPaths(...lists: string[][]): string[] {
  const set = new Set<string>()
  const addWithAncestors = (path: string) => {
    const norm = normalizeFolderPath(path)
    if (!norm) return
    const parts = norm.split(FOLDER_SEP)
    let acc = ''
    for (const part of parts) {
      acc = acc ? `${acc}${FOLDER_SEP}${part}` : part
      set.add(acc)
    }
  }
  for (const list of lists) {
    for (const p of list) addWithAncestors(p)
  }
  return [...set].sort((a, b) => a.localeCompare(b))
}

export function buildFolderForest(paths: string[]): FolderTreeNode[] {
  const all = collectAllFolderPaths(paths)
  const map = new Map<string, FolderTreeNode>()
  for (const p of all) {
    map.set(p, { path: p, name: folderLeafName(p), children: [] })
  }
  const roots: FolderTreeNode[] = []
  const ordered = [...all].sort(
    (a, b) => a.split(FOLDER_SEP).length - b.split(FOLDER_SEP).length || a.localeCompare(b),
  )
  for (const p of ordered) {
    const node = map.get(p)!
    const parent = parentFolderPath(p)
    if (parent && map.has(parent)) map.get(parent)!.children.push(node)
    else roots.push(node)
  }
  const sortRec = (nodes: FolderTreeNode[]) => {
    nodes.sort((a, b) => a.name.localeCompare(b.name))
    for (const n of nodes) sortRec(n.children)
  }
  sortRec(roots)
  return roots
}

export function uniqueSiblingPath(parent: string, baseName: string, existing: string[]): string {
  const taken = new Set(existing.map(normalizeFolderPath))
  let name = sanitizeFolderName(baseName) || 'folder'
  let candidate = childFolderPath(parent, name)
  if (!taken.has(candidate)) return candidate
  for (let i = 2; i < 1000; i++) {
    candidate = childFolderPath(parent, `${name} ${i}`)
    if (!taken.has(candidate)) return candidate
  }
  return childFolderPath(parent, `${name} ${Date.now()}`)
}

export function loadExtraHostGroups(): string[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return collectAllFolderPaths(parsed.map((x) => String(x || '')))
  } catch {
    return []
  }
}

export function saveExtraHostGroups(names: string[]) {
  if (typeof localStorage === 'undefined') return
  const cleaned = collectAllFolderPaths(names)
  localStorage.setItem(KEY, JSON.stringify(cleaned))
}

export function rememberHostGroup(name: string) {
  const n = normalizeFolderPath(name)
  if (!n) return
  const next = loadExtraHostGroups()
  if (!next.includes(n)) {
    next.push(n)
    saveExtraHostGroups(next)
  }
}

/** Remove a folder path and all descendants from the empty-folder list. */
export function forgetHostGroup(name: string) {
  const n = normalizeFolderPath(name)
  if (!n) return
  saveExtraHostGroups(loadExtraHostGroups().filter((p) => !isUnderFolder(p, n)))
}

/** Rewrite empty-folder list when a folder is renamed/moved. */
export function rewriteExtraHostGroups(from: string, to: string) {
  const f = normalizeFolderPath(from)
  if (!f) return
  const next = loadExtraHostGroups().map((p) => rewriteFolderPrefix(p, f, to))
  saveExtraHostGroups(next)
}

/** Duplicate empty subtree under a new sibling path. */
export function copyExtraHostSubtree(from: string, to: string) {
  const f = normalizeFolderPath(from)
  const t = normalizeFolderPath(to)
  if (!f || !t) return
  const extras = loadExtraHostGroups()
  const added = extras.filter((p) => isUnderFolder(p, f)).map((p) => rewriteFolderPrefix(p, f, t))
  saveExtraHostGroups([...extras, ...added, t])
}
