export function formatRelativeTime(iso?: string | null): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const sec = Math.round((Date.now() - t) / 1000)
  if (sec < 45) return '刚刚'
  if (sec < 3600) return `${Math.max(1, Math.round(sec / 60))} 分钟前`
  if (sec < 86400) return `${Math.max(1, Math.round(sec / 3600))} 小时前`
  if (sec < 86400 * 7) return `${Math.max(1, Math.round(sec / 86400))} 天前`
  return new Date(t).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

export function isMacMod() {
  return /Mac|iPhone|iPad/.test(navigator.platform) || /Mac/.test(navigator.userAgent)
}

export function paletteShortcutLabel() {
  return isMacMod() ? '⌘⇧P' : 'Ctrl+Shift+P'
}
