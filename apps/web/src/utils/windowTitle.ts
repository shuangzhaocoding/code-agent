import { getDesktopBridge } from '@/utils/desktop'

const APP_NAME = 'Code Agent'

export function formatWindowTitle(opts: {
  session?: string | null
  workspace?: string | null
}): string {
  const session = (opts.session || '').trim()
  const workspace = (opts.workspace || '').trim()
  if (session && workspace) return `${session} — ${workspace}`
  if (session) return session
  if (workspace) return workspace
  return APP_NAME
}

/** Update browser tab title and desktop taskbar / Dock window title. */
export function applyWindowTitle(title: string) {
  const next = (title || '').trim() || APP_NAME
  if (document.title !== next) document.title = next
  const desktop = getDesktopBridge()
  if (typeof desktop?.setTitle === 'function') {
    void desktop.setTitle(next)
  }
}

export { APP_NAME as WINDOW_TITLE_APP_NAME }
