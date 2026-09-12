import type { TerminalRunRequest } from '@/utils/scriptRun'

/** Pending cwd for “open terminal here” when the terminal panel is not mounted yet. */
let pendingCwd: string | null | undefined
let pendingRun: TerminalRunRequest | undefined

export function queueTerminalCwd(cwd?: string | null) {
  pendingCwd = cwd == null ? '' : cwd
}

/** Returns undefined if nothing queued; empty string means workspace root. */
export function takeTerminalCwd(): string | null | undefined {
  if (pendingCwd === undefined) return undefined
  const next = pendingCwd
  pendingCwd = undefined
  return next
}

export function queueTerminalRun(run: TerminalRunRequest) {
  pendingRun = run
}

export function takeTerminalRun(): TerminalRunRequest | undefined {
  const next = pendingRun
  pendingRun = undefined
  return next
}
