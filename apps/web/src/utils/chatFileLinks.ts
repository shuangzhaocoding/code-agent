/** Detect and open file paths mentioned in chat markdown. */

export type ChatFileRef = {
  /** Path to pass to the workspace file API / editor tab. */
  openPath: string
  /** Workspace-relative path for explorer reveal; null if outside workspace. */
  revealRel: string | null
  line?: number
}

const TRAILING_PUNCT = /[.,;:!?，。；：！？、）】」』>]+$/g
const LINE_SUFFIX = /:(\d+)(?:-\d+)?$/

/** Paths inside prose / inline code (codespans use a looser check). */
const PATH_IN_TEXT =
  /(?:~\/[^\s`"'<>|*?]+|\.{1,2}\/[^\s`"'<>|*?]+|\/(?:[\w.-]+\/)+[^\s`"'<>|*?]+|[A-Za-z]:[\\/][^\s`"'<>|*?]+|(?:[\w.-]+\/)+[\w.-]+\.[a-zA-Z0-9]{1,12})(?::\d+(?:-\d+)?)?/g

function normalizeSlashes(p: string): string {
  return p.replace(/\\/g, '/')
}

function stripWrap(raw: string): string {
  let s = raw.trim()
  if (
    (s.startsWith('"') && s.endsWith('"')) ||
    (s.startsWith("'") && s.endsWith("'")) ||
    (s.startsWith('`') && s.endsWith('`'))
  ) {
    s = s.slice(1, -1).trim()
  }
  return s
}

function stripLineSuffix(path: string): { path: string; line?: number } {
  if (/^[A-Za-z]:[\\/]/.test(path)) return { path }
  if (/^\w+:\/\//.test(path)) return { path }
  const m = LINE_SUFFIX.exec(path)
  if (!m) return { path }
  return { path: path.slice(0, -m[0].length), line: Number(m[1]) }
}

export function looksLikeFilePath(raw: string, opts?: { loose?: boolean }): boolean {
  const s = stripWrap(raw).replace(TRAILING_PUNCT, '')
  if (!s || s.length < 2 || s.length > 512) return false
  if (/^(https?|mailto|data|blob):/i.test(s)) return false
  if (s.includes('://')) return false
  if (/^[\w.+-]+@[\w.-]+$/.test(s)) return false
  if (s === '/' || s === '~' || s === '.' || s === '..') return false

  const { path } = stripLineSuffix(s)
  if (path.startsWith('~/') || path.startsWith('./') || path.startsWith('../')) return true
  if (/^[A-Za-z]:[\\/]/.test(path)) return true
  if (path.startsWith('/') && path.includes('/', 1)) return true
  if (path.includes('/') || path.includes('\\')) {
    if (/\.[a-zA-Z0-9]{1,12}$/.test(path)) return true
    if (path.split(/[/\\]/).filter(Boolean).length >= 2) return true
    if (opts?.loose) return true
  }
  if (opts?.loose && /\.[a-zA-Z0-9]{1,12}$/.test(path) && !path.startsWith('.')) return true
  return false
}

/** Infer OS home from an absolute workspace root when possible. */
export function inferHomeFromRoot(root: string): string | null {
  const n = normalizeSlashes(root.trim())
  if (!n.startsWith('/')) return null
  if (n === '/root' || n.startsWith('/root/')) return '/root'
  const home = n.match(/^(\/home\/[^/]+)/) || n.match(/^(\/Users\/[^/]+)/)
  return home ? home[1] : null
}

export function expandHomePath(path: string, root: string): string {
  const p = normalizeSlashes(path)
  if (p === '~') {
    return inferHomeFromRoot(root) || p
  }
  if (!p.startsWith('~/')) return p
  const home = inferHomeFromRoot(root)
  if (!home) return p
  return `${home}/${p.slice(2)}`
}

export function toWorkspaceRelative(path: string, root: string): string | null {
  if (!root?.trim() || !path) return null
  const normRoot = normalizeSlashes(root.trim()).replace(/\/+$/, '')
  let p = expandHomePath(path, root)
  p = normalizeSlashes(p)
  // Already workspace-relative
  if (!p.startsWith('/') && !p.startsWith('~/') && !/^[A-Za-z]:\//.test(p)) {
    if (p.startsWith('./')) p = p.slice(2)
    while (p.startsWith('../')) return null
    return p || null
  }
  const rootLower = normRoot.toLowerCase()
  const pathLower = p.toLowerCase()
  if (pathLower === rootLower) return ''
  if (pathLower.startsWith(`${rootLower}/`)) {
    return p.slice(normRoot.length + 1)
  }
  return null
}

export function parseChatFileRef(raw: string, workspaceRoot = ''): ChatFileRef | null {
  let s = stripWrap(raw)
  s = s.replace(TRAILING_PUNCT, '')
  if (s.startsWith('file://')) {
    try {
      s = decodeURIComponent(s.replace(/^file:\/\//, ''))
    } catch {
      s = s.replace(/^file:\/\//, '')
    }
  }
  const { path: withoutLine, line } = stripLineSuffix(s)
  if (!looksLikeFilePath(withoutLine, { loose: true })) return null

  const revealRel = workspaceRoot ? toWorkspaceRelative(withoutLine, workspaceRoot) : null
  if (revealRel != null && revealRel !== '') {
    return { openPath: revealRel, revealRel, line }
  }
  return { openPath: withoutLine, revealRel: null, line }
}

function makeFileAnchor(label: string, path: string, line?: number): HTMLAnchorElement {
  const a = document.createElement('a')
  a.href = '#'
  a.className = 'ca-file-link'
  a.setAttribute('data-ca-file', '1')
  a.setAttribute('data-path', path)
  if (line) a.setAttribute('data-line', String(line))
  a.title = line ? `${path}:${line}` : path
  a.textContent = label
  return a
}

function linkifyCodeElement(el: HTMLElement, workspaceRoot: string) {
  const text = el.textContent || ''
  const ref = parseChatFileRef(text, workspaceRoot)
  if (!ref) return
  const a = makeFileAnchor(text, ref.openPath, ref.line)
  el.replaceWith(a)
}

function linkifyTextNode(node: Text, workspaceRoot: string) {
  const text = node.nodeValue || ''
  PATH_IN_TEXT.lastIndex = 0
  if (!PATH_IN_TEXT.test(text)) return
  PATH_IN_TEXT.lastIndex = 0

  const frag = document.createDocumentFragment()
  let last = 0
  let m: RegExpExecArray | null
  while ((m = PATH_IN_TEXT.exec(text))) {
    const raw = m[0]
    const cleaned = raw.replace(TRAILING_PUNCT, '')
    const ref = parseChatFileRef(cleaned, workspaceRoot)
    if (!ref) continue
    if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)))
    frag.appendChild(makeFileAnchor(cleaned, ref.openPath, ref.line))
    const trailing = raw.slice(cleaned.length)
    if (trailing) frag.appendChild(document.createTextNode(trailing))
    last = m.index + raw.length
  }
  if (last === 0) return
  if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)))
  node.parentNode?.replaceChild(frag, node)
}

function shouldSkipElement(el: Element): boolean {
  const tag = el.tagName
  return tag === 'PRE' || tag === 'CODE' || tag === 'A' || tag === 'SCRIPT' || tag === 'STYLE'
}

/**
 * Wrap detectable file paths in sanitized markdown HTML as `.ca-file-link` anchors.
 */
export function linkifyFilePathsInHtml(html: string, workspaceRoot = ''): string {
  if (!html.trim()) return html
  const tpl = document.createElement('template')
  tpl.innerHTML = html

  // Inline codespans
  for (const code of [...tpl.content.querySelectorAll('code')]) {
    if (code.closest('pre')) continue
    linkifyCodeElement(code as HTMLElement, workspaceRoot)
  }

  // Existing anchors whose href looks like a local path
  for (const a of [...tpl.content.querySelectorAll('a[href]')]) {
    const href = a.getAttribute('href') || ''
    if (/^(https?:|mailto:|data:|blob:|#)/i.test(href)) continue
    const ref = parseChatFileRef(href, workspaceRoot)
    if (!ref) continue
    a.classList.add('ca-file-link')
    a.setAttribute('data-ca-file', '1')
    a.setAttribute('data-path', ref.openPath)
    if (ref.line) a.setAttribute('data-line', String(ref.line))
    a.setAttribute('href', '#')
    a.setAttribute('title', ref.line ? `${ref.openPath}:${ref.line}` : ref.openPath)
  }

  // Bare paths in text nodes
  const walker = document.createTreeWalker(tpl.content, NodeFilter.SHOW_TEXT)
  const texts: Text[] = []
  let n = walker.nextNode()
  while (n) {
    const parent = n.parentElement
    if (parent && !shouldSkipElement(parent) && !parent.closest('pre, a, code')) {
      texts.push(n as Text)
    }
    n = walker.nextNode()
  }
  for (const textNode of texts) linkifyTextNode(textNode, workspaceRoot)

  return tpl.innerHTML
}

export function fileLinkFromClickTarget(target: EventTarget | null): { path: string; line?: number } | null {
  if (!(target instanceof Element)) return null
  const el = target.closest('a.ca-file-link, a[data-ca-file]')
  if (!el) return null
  const path = el.getAttribute('data-path') || ''
  if (!path) return null
  const lineRaw = el.getAttribute('data-line')
  const line = lineRaw ? Number(lineRaw) : undefined
  return { path, line: line && Number.isFinite(line) ? line : undefined }
}
