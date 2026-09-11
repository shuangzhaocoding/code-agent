export type MenuBarPosition = 'top' | 'left' | 'right' | 'bottom'

const KEYS = {
  menuPosition: 'ca.menu.position',
} as const

const POSITIONS: MenuBarPosition[] = ['top', 'left', 'right', 'bottom']

export function isMenuBarPosition(value: unknown): value is MenuBarPosition {
  return value === 'top' || value === 'left' || value === 'right' || value === 'bottom'
}

export function getMenuBarPosition(defaultValue: MenuBarPosition = 'top'): MenuBarPosition {
  try {
    const raw = localStorage.getItem(KEYS.menuPosition)
    return isMenuBarPosition(raw) ? raw : defaultValue
  } catch {
    return defaultValue
  }
}

export function setMenuBarPosition(value: MenuBarPosition) {
  try {
    localStorage.setItem(KEYS.menuPosition, value)
  } catch {
    /* ignore quota */
  }
  window.dispatchEvent(new CustomEvent('ca-menu-position', { detail: { position: value } }))
}

export const MENU_BAR_POSITIONS = POSITIONS
