import { localeMeta, t } from '@/i18n'

export function formatRelativeTime(iso?: string | null): string {
  if (!iso) return ''
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return ''
  const sec = Math.round((Date.now() - ts) / 1000)
  if (sec < 45) return t('time.justNow')
  if (sec < 3600) return t('time.minutesAgo', { n: Math.max(1, Math.round(sec / 60)) })
  if (sec < 86400) return t('time.hoursAgo', { n: Math.max(1, Math.round(sec / 3600)) })
  if (sec < 86400 * 7) return t('time.daysAgo', { n: Math.max(1, Math.round(sec / 86400)) })
  return new Date(ts).toLocaleDateString(localeMeta().bcp47, { month: 'short', day: 'numeric' })
}

export function isMacMod() {
  return /Mac|iPhone|iPad/.test(navigator.platform) || /Mac/.test(navigator.userAgent)
}

export function paletteShortcutLabel() {
  return isMacMod() ? '⌘⇧P' : 'Ctrl+Shift+P'
}
