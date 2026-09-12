/** Runners for script files opened in the editor. */

const RUNNERS: Record<string, { unix: string; win: string }> = {
  py: { unix: 'python3', win: 'python' },
  pyw: { unix: 'python3', win: 'python' },
  sh: { unix: 'bash', win: 'bash' },
  bash: { unix: 'bash', win: 'bash' },
  zsh: { unix: 'zsh', win: 'zsh' },
  js: { unix: 'node', win: 'node' },
  mjs: { unix: 'node', win: 'node' },
  cjs: { unix: 'node', win: 'node' },
  rb: { unix: 'ruby', win: 'ruby' },
  pl: { unix: 'perl', win: 'perl' },
}

export type TerminalRunRequest = {
  command: string
  cwd?: string
}

export function isWindowsRoot(root: string | null | undefined): boolean {
  const value = (root || '').trim()
  return /^[A-Za-z]:[\\/]/.test(value) || value.includes('\\')
}

export function scriptExtension(path: string): string {
  const name = (path.split(/[\\/]/).pop() || '').toLowerCase()
  const index = name.lastIndexOf('.')
  return index >= 0 ? name.slice(index + 1) : ''
}

export function isRunnableScript(path: string | null | undefined): boolean {
  if (!path) return false
  return scriptExtension(path) in RUNNERS
}

function shellQuote(value: string, windows: boolean): string {
  if (windows) return `"${value.replace(/"/g, '\\"')}"`
  return `'${value.replace(/'/g, `'\\''`)}'`
}

/** Shell line that cds to the file dir then runs the interpreter. */
export function scriptRunCommand(
  path: string,
  opts?: { windows?: boolean },
): string | null {
  const runner = RUNNERS[scriptExtension(path)]
  if (!runner) return null
  const windows = Boolean(opts?.windows)
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean)
  const name = parts.pop() || path
  const dir = parts.join('/')
  const bin = windows ? runner.win : runner.unix
  const run = `${bin} ${shellQuote(name, windows)}`
  if (!dir) return run
  const cd = `cd ${shellQuote(dir, windows)}`
  return windows ? `${cd}; ${run}` : `${cd} && ${run}`
}
