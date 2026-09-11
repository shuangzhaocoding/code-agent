/** Synthetic path used for terminal selection mentions in the composer / chat. */
export const TERMINAL_MENTION_PATH = 'terminal'

export function isTerminalMentionPath(path: string | null | undefined) {
  return path === TERMINAL_MENTION_PATH
}

export type TerminalSelectionRange = {
  text: string
  startLine: number
  endLine: number
}

/** 1-based buffer line range from an xterm selection, if any. */
export function terminalSelectionRange(term: {
  getSelection: () => string
  getSelectionPosition?: () => { start: { y: number }; end: { y: number } } | undefined
} | null | undefined): TerminalSelectionRange | null {
  const text = term?.getSelection()?.replace(/\r\n/g, '\n') || ''
  const trimmed = text.trim()
  if (!trimmed) return null
  const pos = term?.getSelectionPosition?.()
  const startLine = pos ? Math.min(pos.start.y, pos.end.y) + 1 : 1
  const endLine = pos ? Math.max(pos.start.y, pos.end.y) + 1 : Math.max(1, trimmed.split('\n').length)
  return { text: trimmed, startLine, endLine }
}
