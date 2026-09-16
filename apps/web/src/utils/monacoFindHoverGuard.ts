/**
 * Monaco find-widget buttons use HoverStyle.Pointer tips that often render on top
 * of the icon (esp. Close / Previous at the top edge). That overlay steals hits,
 * so the tip flickers and the button cannot be clicked.
 *
 * Capture-phase mouseover stop keeps Monaco from opening those tips; aria-label
 * is copied to title so appTooltip / native title can show a stable tip instead.
 */

const FIND_BTN =
  '.find-widget [role="button"], .find-widget [role="checkbox"], .find-widget .button'

function onFindWidgetMouseOver(event: Event) {
  const target = event.target
  if (!(target instanceof Element)) return
  const btn = target.closest(FIND_BTN)
  if (!(btn instanceof HTMLElement)) return
  const label = (btn.getAttribute('aria-label') || '').trim()
  if (label) {
    if (btn.getAttribute('title') !== label) btn.setAttribute('title', label)
    if (btn.getAttribute('data-app-tooltip') !== label) btn.setAttribute('data-app-tooltip', label)
  }
  event.stopImmediatePropagation()
}

/** Force pointer-events off on Monaco hover shells that already opened. */
function neutralizeHoverShell(node: Element) {
  const mark = (el: HTMLElement) => {
    el.style.setProperty('pointer-events', 'none', 'important')
  }
  if (node instanceof HTMLElement) {
    if (
      node.classList.contains('context-view') &&
      node.querySelector('.monaco-hover, .workbench-hover-container, .workbench-hover')
    ) {
      mark(node)
    }
    if (
      node.classList.contains('workbench-hover-container') ||
      (node.classList.contains('monaco-hover') && node.classList.contains('workbench-hover'))
    ) {
      mark(node)
      const shell = node.closest('.context-view')
      if (shell instanceof HTMLElement) mark(shell)
    }
  }
  node.querySelectorAll?.(
    '.context-view:has(.monaco-hover), .context-view:has(.workbench-hover-container), .workbench-hover-container, .monaco-hover.workbench-hover',
  ).forEach((el) => {
    if (el instanceof HTMLElement) mark(el)
  })
}

let installed = false
let hoverObs: MutationObserver | null = null

export function installMonacoFindHoverGuard() {
  if (installed || typeof document === 'undefined') return
  installed = true
  document.addEventListener('mouseover', onFindWidgetMouseOver, true)
  hoverObs = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const n of m.addedNodes) {
        if (n instanceof Element) neutralizeHoverShell(n)
      }
    }
  })
  hoverObs.observe(document.body, { childList: true, subtree: true })
}

export function uninstallMonacoFindHoverGuard() {
  if (!installed) return
  document.removeEventListener('mouseover', onFindWidgetMouseOver, true)
  hoverObs?.disconnect()
  hoverObs = null
  installed = false
}
