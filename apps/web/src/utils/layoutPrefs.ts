const KEYS = {
  sidebarCollapsed: 'ca.sidebar.collapsed',
  trajectoryOpen: 'ca.trajectory.open',
} as const

function readBool(key: string, defaultValue: boolean): boolean {
  const saved = localStorage.getItem(key)
  if (saved === '1') return true
  if (saved === '0') return false
  return defaultValue
}

function writeBool(key: string, value: boolean) {
  localStorage.setItem(key, value ? '1' : '0')
}

export function getSidebarCollapsed(defaultValue = false): boolean {
  return readBool(KEYS.sidebarCollapsed, defaultValue)
}

export function setSidebarCollapsed(value: boolean) {
  writeBool(KEYS.sidebarCollapsed, value)
}

export function getTrajectoryOpen(defaultValue = true): boolean {
  return readBool(KEYS.trajectoryOpen, defaultValue)
}

export function setTrajectoryOpen(value: boolean) {
  writeBool(KEYS.trajectoryOpen, value)
}
