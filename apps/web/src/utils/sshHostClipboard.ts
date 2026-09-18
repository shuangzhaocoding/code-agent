/** In-app clipboard for SSH host sessions (connection + workspaces, no secrets). */

export type SshHostClipboardWorkspace = {
  root_path: string
  name?: string
}

export type SshHostClipboard = {
  ssh_display_name?: string
  ssh_group?: string
  ssh_host: string
  ssh_port: number
  ssh_user: string
  /** Source workspace id — paste reuses secret blob. */
  reuse_ssh_from?: string
  label?: string
  workspaces: SshHostClipboardWorkspace[]
  copied_at: number
}

let clip: SshHostClipboard | null = null
const listeners = new Set<() => void>()

export function getSshHostClipboard(): SshHostClipboard | null {
  return clip
}

export function hasSshHostClipboard(): boolean {
  return Boolean(clip?.ssh_host && clip.workspaces?.length)
}

export function setSshHostClipboard(next: Omit<SshHostClipboard, 'copied_at'> | null): void {
  clip = next
    ? {
        ...next,
        ssh_host: String(next.ssh_host || '').trim(),
        ssh_port: Number(next.ssh_port) || 22,
        ssh_user: String(next.ssh_user || '').trim(),
        ssh_display_name: (next.ssh_display_name || '').trim() || undefined,
        ssh_group: (next.ssh_group || '').trim() || undefined,
        reuse_ssh_from: next.reuse_ssh_from || undefined,
        label: (next.label || '').trim() || undefined,
        workspaces: (next.workspaces || [])
          .map((w) => ({
            root_path: String(w.root_path || '').trim(),
            name: (w.name || '').trim() || undefined,
          }))
          .filter((w) => w.root_path),
        copied_at: Date.now(),
      }
    : null
  if (clip && !clip.workspaces.length) clip = null
  for (const fn of listeners) {
    try {
      fn()
    } catch {
      /* ignore */
    }
  }
}

export function subscribeSshHostClipboard(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function formatSshEndpoint(clipOr: {
  ssh_host?: string
  ssh_port?: number
  ssh_user?: string
}): string {
  const host = clipOr.ssh_host || 'unknown'
  const port = clipOr.ssh_port || 22
  const user = clipOr.ssh_user || ''
  return user ? `${user}@${host}:${port}` : `${host}:${port}`
}

export function uniqueHostCopyName(base: string, existingLabels: string[], suffix: string): string {
  const root = (base || '').trim() || 'SSH'
  const taken = new Set(existingLabels.map((s) => s.trim()).filter(Boolean))
  let name = `${root} ${suffix}`.trim()
  let i = 2
  while (taken.has(name)) {
    name = `${root} ${suffix} ${i}`
    i += 1
  }
  return name
}
