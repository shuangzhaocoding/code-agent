export type Theme = 'light' | 'dark'

const KEY = 'ca.theme'

export function getStoredTheme(): Theme {
  const saved = localStorage.getItem(KEY)
  if (saved === 'dark' || saved === 'light') return saved
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark'
  return 'light'
}

export function applyTheme(theme: Theme): Theme {
  const next = theme === 'dark' ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', next)
  localStorage.setItem(KEY, next)
  window.dispatchEvent(new CustomEvent('ca-theme', { detail: next }))
  return next
}

export function toggleTheme(): Theme {
  const current = (document.documentElement.getAttribute('data-theme') as Theme) || getStoredTheme()
  return applyTheme(current === 'dark' ? 'light' : 'dark')
}

export function initTheme(): Theme {
  return applyTheme(getStoredTheme())
}

export function currentTheme(): Theme {
  return (document.documentElement.getAttribute('data-theme') as Theme) || getStoredTheme()
}
