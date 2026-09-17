/** Strip ANSI / VT escape sequences (colors, styles, cursor moves). */

// Complete CSI / OSC / 2-byte ESC
// eslint-disable-next-line no-control-regex
const ANSI_RE =
  /(?:\u001B\][^\u0007\u001B]*(?:\u0007|\u001B\\)|\u001B[@-Z\\-_]|\u001B\[[0-?]*[ -/]*[@-~]|\u009B[0-?]*[ -/]*[@-~])/g

// Orphan SGR when ESC was lost mid-stream: [32m [0m [1;36m
const ORPHAN_SGR_RE = /\[[\d;]{0,16}m/g

// Incomplete ESC suffix held across chunks
// eslint-disable-next-line no-control-regex
const INCOMPLETE_RE = /(?:\u001B$|\u001B\[[0-?]*[ -/]*$|\u001B\][^\u0007\u001B]*$|\u009B[0-?]*[ -/]*$)$/

export function stripAnsi(text: string): string {
  if (!text) return text
  return text.replace(ANSI_RE, '').replace(ORPHAN_SGR_RE, '')
}

/** Stateful stripper for streaming stdout/stderr chunks. */
export class AnsiStreamFilter {
  private pending = ''

  feed(chunk: string): string {
    let data = `${this.pending}${chunk || ''}`
    this.pending = ''
    if (!data) return ''
    const m = INCOMPLETE_RE.exec(data)
    if (m) {
      this.pending = m[0] || ''
      data = data.slice(0, m.index)
    }
    return stripAnsi(data)
  }

  flush(): string {
    const leftover = this.pending
    this.pending = ''
    return leftover ? stripAnsi(leftover) : ''
  }
}
