export type GitTreeFile = {
  path: string
  status: string
  additions: number
  deletions: number
}

export type GitTreeItem = {
  name: string
  path: string
  kind: 'dir' | 'file'
  additions: number
  deletions: number
  status?: string
  children?: GitTreeItem[]
}

export function buildGitFileTree(files: GitTreeFile[]): GitTreeItem[] {
  const root: GitTreeItem[] = []
  const dirs = new Map<string, GitTreeItem>()

  function ensureDir(dirPath: string): GitTreeItem | null {
    if (!dirPath) return null
    const existing = dirs.get(dirPath)
    if (existing) return existing
    const parentPath = dirPath.includes('/') ? dirPath.slice(0, dirPath.lastIndexOf('/')) : ''
    const node: GitTreeItem = {
      name: dirPath.split('/').pop() || dirPath,
      path: dirPath,
      kind: 'dir',
      additions: 0,
      deletions: 0,
      children: [],
    }
    dirs.set(dirPath, node)
    const parent = parentPath ? ensureDir(parentPath) : null
    if (parent) parent.children!.push(node)
    else root.push(node)
    return node
  }

  for (const file of files) {
    const parentPath = file.path.includes('/') ? file.path.slice(0, file.path.lastIndexOf('/')) : ''
    const node: GitTreeItem = {
      name: file.path.split('/').pop() || file.path,
      path: file.path,
      kind: 'file',
      additions: file.additions,
      deletions: file.deletions,
      status: file.status,
    }
    const parent = parentPath ? ensureDir(parentPath) : null
    if (parent) parent.children!.push(node)
    else root.push(node)
  }

  function rollup(nodes: GitTreeItem[]) {
    nodes.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    for (const node of nodes) {
      if (node.kind === 'dir') {
        rollup(node.children || [])
        node.additions = (node.children || []).reduce((sum, child) => sum + child.additions, 0)
        node.deletions = (node.children || []).reduce((sum, child) => sum + child.deletions, 0)
      }
    }
  }
  rollup(root)
  return root
}

export function collectGitDirPaths(nodes: GitTreeItem[], out: string[] = []) {
  for (const node of nodes) {
    if (node.kind === 'dir') {
      out.push(node.path)
      collectGitDirPaths(node.children || [], out)
    }
  }
  return out
}
