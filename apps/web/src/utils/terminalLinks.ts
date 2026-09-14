/** xterm link helpers: clickable URLs + workspace file/dir paths. */
import type { IDisposable, ILink, ILinkProvider, IViewportRange, Terminal } from '@xterm/xterm'
import { findFilePathMatches, parseChatFileRef } from '@/utils/chatFileLinks'
import { isHttpUrl, openExternalUrl, preferInAppPreview, urlOpenMode } from '@/utils/openUrl'
import { openUrlPreview } from '@/composables/useUrlPreview'
import { t } from '@/i18n'

const TIP_CLASS = 'ca-term-link-tip'

export function handleTerminalUrlClick(event: MouseEvent, uri: string) {
  const url = (uri || '').trim()
  if (!url) return
  if (preferInAppPreview(event) && isHttpUrl(url)) {
    openUrlPreview(url)
    return
  }
  void openExternalUrl(url)
}

/** Same wording as chat URL chips. */
export function terminalUrlHoverLabel(): string {
  return t(urlOpenMode() === 'browser' ? 'chat.urlLinkTitleBrowser' : 'chat.urlLinkTitle')
}

export function terminalPathHoverLabel(path: string, line?: number): string {
  if (line) return t('terminal.openFileAtLineHint', { path, line })
  if (pathLooksLikeDirectory(path)) return t('terminal.openDirHint', { path })
  return t('terminal.openFileHint', { path })
}

type TipState = {
  el: HTMLDivElement | null
  term: Terminal | null
}

const tipState: TipState = { el: null, term: null }

function hideTerminalLinkTip() {
  tipState.el?.remove()
  tipState.el = null
  tipState.term = null
}

function showTerminalLinkTip(term: Terminal, event: MouseEvent, label: string) {
  const root = term.element
  if (!root || !label) {
    hideTerminalLinkTip()
    return
  }
  let tip = tipState.el
  if (!tip || tipState.term !== term) {
    hideTerminalLinkTip()
    tip = document.createElement('div')
    tip.className = `xterm-hover ${TIP_CLASS}`
    tip.setAttribute('role', 'tooltip')
    root.appendChild(tip)
    tipState.el = tip
    tipState.term = term
  }
  tip.textContent = label

  const rootRect = root.getBoundingClientRect()
  const pad = 10
  let left = event.clientX - rootRect.left + pad
  let top = event.clientY - rootRect.top + 18
  tip.style.left = `${left}px`
  tip.style.top = `${top}px`
  tip.style.visibility = 'hidden'
  // Clamp after layout so the tip stays inside the terminal viewport.
  const tipRect = tip.getBoundingClientRect()
  const maxLeft = Math.max(4, rootRect.width - tipRect.width - 4)
  const maxTop = Math.max(4, rootRect.height - tipRect.height - 4)
  left = Math.min(Math.max(4, left), maxLeft)
  top = Math.min(Math.max(4, top), maxTop)
  tip.style.left = `${left}px`
  tip.style.top = `${top}px`
  tip.style.visibility = 'visible'
}

function lineText(term: Terminal, bufferLineNumber: number): string {
  const line = term.buffer.active.getLine(bufferLineNumber - 1)
  if (!line) return ''
  return line.translateToString(false)
}

function pathLooksLikeDirectory(path: string): boolean {
  if (path.endsWith('/')) return true
  const leaf = path.split('/').filter(Boolean).pop() || ''
  if (!leaf) return true
  if (!/\.[a-zA-Z0-9]{1,12}$/.test(leaf)) return true
  return false
}

export type TerminalPathNavigator = {
  workspaceRoot: () => string
  loadTree: (path: string) => Promise<void>
  childrenOf: (path: string) => Array<{ path: string; is_dir: boolean }>
  openFile: (path: string, line?: number) => void | Promise<void>
  openDirectory: (path: string) => void | Promise<void>
}

function parentOf(path: string): string {
  const parts = path.replace(/\/+$/, '').split('/').filter(Boolean)
  parts.pop()
  return parts.join('/')
}

export async function navigateTerminalPath(nav: TerminalPathNavigator, raw: string, line?: number) {
  const root = nav.workspaceRoot()
  const ref = parseChatFileRef(raw, root)
  if (!ref) return
  const path = ref.openPath.replace(/\/+$/, '')
  const targetLine = line ?? ref.line
  if (targetLine) {
    await nav.openFile(path, targetLine)
    return
  }

  const parent = parentOf(path)
  try {
    await nav.loadTree(parent)
  } catch {
    /* tree may be cold */
  }
  const item = nav.childrenOf(parent).find((entry) => entry.path === path)
  if (item?.is_dir) {
    await nav.openDirectory(path)
    return
  }
  if (!item && pathLooksLikeDirectory(path)) {
    try {
      await nav.openDirectory(path)
      return
    } catch {
      /* fall through and open as file */
    }
  }
  await nav.openFile(path)
}

/** Clickable file / directory paths in terminal output. */
export function createTerminalPathLinkProvider(
  term: Terminal,
  nav: TerminalPathNavigator,
): ILinkProvider {
  return {
    provideLinks(bufferLineNumber, callback) {
      const text = lineText(term, bufferLineNumber)
      if (!text.trim()) {
        callback(undefined)
        return
      }
      const root = nav.workspaceRoot()
      const matches = findFilePathMatches(text, root)
      if (!matches.length) {
        callback(undefined)
        return
      }
      const links: ILink[] = matches.map((m) => {
        const startX = m.start + 1
        const endX = m.end
        const tipLabel = terminalPathHoverLabel(m.ref.openPath, m.ref.line)
        return {
          text: m.raw,
          range: {
            start: { x: startX, y: bufferLineNumber },
            end: { x: Math.max(startX, endX), y: bufferLineNumber },
          },
          decorations: { pointerCursor: true, underline: true },
          activate: (_event, linkText) => {
            hideTerminalLinkTip()
            void navigateTerminalPath(nav, linkText || m.raw)
          },
          hover: (event) => {
            showTerminalLinkTip(term, event, tipLabel)
          },
          leave: () => {
            hideTerminalLinkTip()
          },
          dispose: () => {
            hideTerminalLinkTip()
          },
        }
      })
      callback(links)
    },
  }
}

export function attachTerminalPathLinks(term: Terminal, nav: TerminalPathNavigator): IDisposable {
  return term.registerLinkProvider(createTerminalPathLinkProvider(term, nav))
}

/** Hover/leave handlers for WebLinksAddon options. */
export function terminalUrlLinkHoverOptions(term: Terminal): {
  hover: (event: MouseEvent, text: string, location: IViewportRange) => void
  leave: (event: MouseEvent, text: string) => void
} {
  return {
    hover: (event) => {
      showTerminalLinkTip(term, event, terminalUrlHoverLabel())
    },
    leave: () => {
      hideTerminalLinkTip()
    },
  }
}
