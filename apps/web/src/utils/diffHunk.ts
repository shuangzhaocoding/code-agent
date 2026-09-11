/** Monaco-compatible line change (1-based; 0 end = insert/delete). */
export type LineChangeLike = {
  originalStartLineNumber: number
  originalEndLineNumber: number
  modifiedStartLineNumber: number
  modifiedEndLineNumber: number
}

function splitLines(text: string): string[] {
  return text.split('\n')
}

function joinLines(lines: string[]): string {
  return lines.join('\n')
}

/**
 * Accept one hunk: fold the modified side of `change` into `before`.
 * Result is the new baseline (partial accept).
 */
export function acceptHunkIntoBefore(before: string, after: string, change: LineChangeLike): string {
  const b = splitLines(before)
  const a = splitLines(after)
  const { originalStartLineNumber: oStart, originalEndLineNumber: oEnd } = change
  const { modifiedStartLineNumber: mStart, modifiedEndLineNumber: mEnd } = change

  const at = oEnd === 0 ? Math.max(0, oStart) : Math.max(0, oStart - 1)
  const remove = oEnd === 0 ? 0 : Math.max(0, oEnd - oStart + 1)
  const insert = mEnd === 0 ? [] : a.slice(Math.max(0, mStart - 1), mEnd)

  return joinLines([...b.slice(0, at), ...insert, ...b.slice(at + remove)])
}

/**
 * Reject one hunk: fold the original side of `change` into `after`.
 * Result is the new agent result with that hunk undone.
 */
export function rejectHunkFromAfter(before: string, after: string, change: LineChangeLike): string {
  const b = splitLines(before)
  const a = splitLines(after)
  const { originalStartLineNumber: oStart, originalEndLineNumber: oEnd } = change
  const { modifiedStartLineNumber: mStart, modifiedEndLineNumber: mEnd } = change

  const at = mEnd === 0 ? Math.max(0, mStart) : Math.max(0, mStart - 1)
  const remove = mEnd === 0 ? 0 : Math.max(0, mEnd - mStart + 1)
  const insert = oEnd === 0 ? [] : b.slice(Math.max(0, oStart - 1), oEnd)

  return joinLines([...a.slice(0, at), ...insert, ...a.slice(at + remove)])
}

export function textsEqual(a: string, b: string): boolean {
  return a === b
}
