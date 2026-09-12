import { useAppStore } from '@/stores/app'
import { getDesktopBridge } from '@/utils/desktop'

const BLOCKED = /^(javascript|data|blob|vbscript|file):/i

/** http(s) / mailto only — never javascript: or in-app hash. */
export function safeExternalUrl(raw: string, base = typeof window !== 'undefined' ? window.location.href : undefined): string | null {
  const href = (raw || '').trim()
  if (!href || href.startsWith('#') || BLOCKED.test(href)) return null
  try {
    const url = new URL(href, base)
    if (url.protocol === 'mailto:') return url.href
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
    return url.href
  } catch {
    return null
  }
}

export function isHttpUrl(url: string): boolean {
  return /^https?:/i.test(url)
}

export type UrlOpenMode = 'app' | 'browser'

export function urlOpenMode(): UrlOpenMode {
  const value = useAppStore().settings?.values?.['ui.url_preview']
  return value === 'browser' ? 'browser' : 'app'
}

/** Default from settings; Shift / Ctrl / Cmd / middle-click inverts. */
export function preferInAppPreview(e: MouseEvent): boolean {
  const invert = e.shiftKey || e.metaKey || e.ctrlKey || e.button === 1
  return urlOpenMode() === 'app' ? !invert : invert
}

/** External chat / markdown link (not a workspace file chip). */
export function chatExternalHref(target: EventTarget | null): string | null {
  if (!(target instanceof Element)) return null
  const anchor = target.closest('a[href]')
  if (!anchor) return null
  if (anchor.classList.contains('ca-file-link') || anchor.getAttribute('data-ca-file')) return null
  return safeExternalUrl(anchor.getAttribute('href') || '')
}

export async function openExternalUrl(raw: string): Promise<boolean> {
  const url = safeExternalUrl(raw)
  if (!url) return false
  const desktop = getDesktopBridge()
  if (typeof desktop?.openExternal === 'function') {
    try {
      return Boolean(await desktop.openExternal(url))
    } catch {
      return false
    }
  }
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  return opened != null
}
