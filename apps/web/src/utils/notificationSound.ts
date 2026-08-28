const PREFS = {
  taskComplete: 'ca.sound.taskComplete',
  approval: 'ca.sound.approval',
} as const

let audioCtx: AudioContext | null = null
let unlockInstalled = false
const playedApprovals = new Set<string>()

function readEnabled(key: string, defaultValue = true): boolean {
  if (typeof localStorage === 'undefined') return defaultValue
  const saved = localStorage.getItem(key)
  if (saved === '0') return false
  if (saved === '1') return true
  return defaultValue
}

function ensureAudio(): AudioContext | null {
  if (typeof window === 'undefined') return null
  if (!audioCtx) audioCtx = new AudioContext()
  if (audioCtx.state === 'suspended') void audioCtx.resume()
  return audioCtx
}

function installUnlock() {
  if (unlockInstalled || typeof window === 'undefined') return
  unlockInstalled = true
  const unlock = () => {
    ensureAudio()
  }
  window.addEventListener('pointerdown', unlock, { once: true, passive: true })
  window.addEventListener('keydown', unlock, { once: true })
}

function playTone(
  frequency: number,
  startOffset: number,
  duration: number,
  volume = 0.14,
  type: OscillatorType = 'sine',
) {
  const ctx = ensureAudio()
  if (!ctx) return
  const start = ctx.currentTime + startOffset
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(frequency, start)
  gain.gain.setValueAtTime(0.0001, start)
  gain.gain.exponentialRampToValueAtTime(Math.max(volume, 0.0001), start + 0.015)
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration)
  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(start)
  osc.stop(start + duration + 0.04)
}

export function isTaskCompleteSoundEnabled(): boolean {
  return readEnabled(PREFS.taskComplete, true)
}

export function isApprovalSoundEnabled(): boolean {
  return readEnabled(PREFS.approval, true)
}

export function setTaskCompleteSoundEnabled(enabled: boolean) {
  localStorage.setItem(PREFS.taskComplete, enabled ? '1' : '0')
}

export function setApprovalSoundEnabled(enabled: boolean) {
  localStorage.setItem(PREFS.approval, enabled ? '1' : '0')
}

/** Pleasant two-note chime when an agent run finishes successfully. */
export function playTaskCompleteSound() {
  installUnlock()
  if (!isTaskCompleteSoundEnabled()) return
  playTone(523.25, 0, 0.11)
  playTone(659.25, 0.13, 0.16, 0.12)
}

/** Urgent double alert when human approval is required. */
export function playApprovalAlertSound() {
  installUnlock()
  if (!isApprovalSoundEnabled()) return
  playTone(880, 0, 0.09, 0.16, 'triangle')
  playTone(880, 0.16, 0.09, 0.16, 'triangle')
  playTone(698.46, 0.34, 0.14, 0.14, 'square')
}

export function notifyApprovalRequired(approvalId?: string) {
  if (approvalId) {
    if (playedApprovals.has(approvalId)) return
    playedApprovals.add(approvalId)
    if (playedApprovals.size > 200) {
      playedApprovals.clear()
      playedApprovals.add(approvalId)
    }
  }
  playApprovalAlertSound()
}
