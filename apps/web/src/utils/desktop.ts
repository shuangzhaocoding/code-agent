export type DesktopPlatform = 'win32' | 'darwin' | 'linux' | string

export type CodeAgentDesktop = {
  isDesktop?: boolean
  platform?: DesktopPlatform
  customTitleBar?: boolean
  /** Linux frameless: draw min/max/close in renderer (Windows uses titleBarOverlay). */
  needsWindowControls?: boolean
  titleBarHeight?: number
  pickDirectory?: () => Promise<string | null>
  setTheme?: (theme: 'light' | 'dark') => void | Promise<string>
  getTheme?: () => Promise<'light' | 'dark' | string>
  newWindow?: () => Promise<boolean>
  setTitle?: (title: string) => void | Promise<void>
  openExternal?: (url: string) => Promise<boolean>
  /** Open a local filesystem path in the OS file manager / default app. */
  openPath?: (targetPath: string) => Promise<boolean>
  windowMinimize?: () => Promise<void>
  windowMaximizeToggle?: () => Promise<boolean>
  windowClose?: () => Promise<void>
  isMaximized?: () => Promise<boolean>
}

export const DESKTOP_TITLEBAR_HEIGHT = 38

export function getDesktopBridge(): CodeAgentDesktop | undefined {
  return (window as Window & { codeAgentDesktop?: CodeAgentDesktop }).codeAgentDesktop
}

export function isDesktopApp(): boolean {
  return Boolean(getDesktopBridge()?.isDesktop)
}

/** Custom title bar on all desktop platforms (Win overlay / mac traffic lights / Linux custom buttons). */
export function hasCustomTitleBar(): boolean {
  const desktop = getDesktopBridge()
  if (!desktop?.isDesktop) return false
  if (typeof desktop.customTitleBar === 'boolean') return desktop.customTitleBar
  return desktop.platform === 'win32' || desktop.platform === 'darwin' || desktop.platform === 'linux'
}

export function needsDesktopWindowControls(): boolean {
  const desktop = getDesktopBridge()
  if (!desktop?.isDesktop) return false
  if (typeof desktop.needsWindowControls === 'boolean') return desktop.needsWindowControls
  return desktop.platform === 'linux'
}

export function desktopPlatform(): DesktopPlatform | null {
  return getDesktopBridge()?.platform || null
}

/** Mark document for title-bar CSS (drag insets, platform padding). */
export function initDesktopChrome() {
  const desktop = getDesktopBridge()
  if (!desktop?.isDesktop) return
  const root = document.documentElement
  root.classList.add('is-desktop')
  if (desktop.platform) root.dataset.desktopPlatform = String(desktop.platform)
  if (hasCustomTitleBar()) {
    root.classList.add('has-custom-titlebar')
    root.style.setProperty(
      '--desktop-titlebar-height',
      `${desktop.titleBarHeight || DESKTOP_TITLEBAR_HEIGHT}px`,
    )
  }
}

/** Open another desktop window (shared local backend). */
export async function openDesktopWindow(): Promise<boolean> {
  const desktop = getDesktopBridge()
  if (!desktop?.isDesktop || typeof desktop.newWindow !== 'function') return false
  try {
    return Boolean(await desktop.newWindow())
  } catch {
    return false
  }
}
