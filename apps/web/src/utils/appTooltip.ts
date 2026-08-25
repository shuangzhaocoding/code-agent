const DELAY_MS = 200
const GAP = 8
const SKIP = new Set(['IFRAME', 'HTML', 'BODY', 'TITLE'])

let tip: HTMLDivElement | null = null
let showTimer = 0
let hideTimer = 0
let active: HTMLElement | null = null

function ensureTip() {
  if (tip) return tip
  tip = document.createElement('div')
  tip.className = 'app-tooltip'
  tip.setAttribute('role', 'tooltip')
  tip.hidden = true
  document.body.appendChild(tip)
  return tip
}

function readTitle(el: HTMLElement) {
  const fromData = el.getAttribute('data-app-tooltip')
  const fromTitle = el.getAttribute('title')
  const text = (fromTitle || fromData || '').trim()
  if (fromTitle) {
    el.setAttribute('data-app-tooltip', fromTitle)
    el.removeAttribute('title')
  }
  return text
}

function findHost(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof Element)) return null
  const el = target.closest('[title], [data-app-tooltip]')
  if (!(el instanceof HTMLElement)) return null
  if (SKIP.has(el.tagName)) return null
  if (el.classList.contains('app-tooltip')) return null
  if (el.closest('.tiny-tooltip, .tr-tooltip, .app-tooltip')) return null
  return el
}

function normalize(text: string) {
  return text.replace(/\s+/g, ' ').trim()
}

function isOverflowing(el: HTMLElement) {
  if (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1) return true
  for (const node of el.querySelectorAll<HTMLElement>('*')) {
    const style = getComputedStyle(node)
    if (style.overflow === 'visible' && style.textOverflow !== 'ellipsis') continue
    if (node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 1) return true
  }
  return false
}

function shouldShow(host: HTMLElement, text: string) {
  if (isOverflowing(host)) return true
  const visible = normalize(host.innerText || '')
  if (!visible) return true
  return visible !== normalize(text)
}

function isComfortable(text: string) {
  return text.length > 20 || /[/\\\n]/.test(text)
}

function place(host: HTMLElement) {
  const node = ensureTip()
  const rect = host.getBoundingClientRect()
  const tw = node.offsetWidth
  const th = node.offsetHeight
  let top = rect.top - th - GAP
  let placement = 'top'
  if (top < GAP) {
    top = rect.bottom + GAP
    placement = 'bottom'
  }
  let left = rect.left + rect.width / 2 - tw / 2
  left = Math.min(window.innerWidth - tw - GAP, Math.max(GAP, left))
  node.dataset.placement = placement
  node.style.top = `${Math.round(top)}px`
  node.style.left = `${Math.round(left)}px`
}

function show(host: HTMLElement, text: string) {
  const node = ensureTip()
  node.textContent = text
  node.classList.toggle('is-comfortable', isComfortable(text))
  node.hidden = false
  node.classList.add('is-visible')
  place(host)
  active = host
}

function hide() {
  window.clearTimeout(showTimer)
  window.clearTimeout(hideTimer)
  showTimer = 0
  if (!tip) return
  tip.classList.remove('is-visible')
  hideTimer = window.setTimeout(() => {
    if (tip) tip.hidden = true
  }, 120)
  if (active) {
    const stored = active.getAttribute('data-app-tooltip')
    if (stored && !active.getAttribute('title')) active.setAttribute('title', stored)
  }
  active = null
}

function onPointerOver(event: PointerEvent) {
  const host = findHost(event.target)
  if (!host) return
  const from = event.relatedTarget
  if (from instanceof Node && host.contains(from)) return
  const text = readTitle(host)
  if (!text || !shouldShow(host, text)) return
  if (host === active && tip && !tip.hidden) {
    if (tip.textContent !== text) {
      tip.textContent = text
      tip.classList.toggle('is-comfortable', isComfortable(text))
      place(host)
    }
    return
  }
  if (active && active !== host) hide()
  window.clearTimeout(showTimer)
  showTimer = window.setTimeout(() => {
    if (!shouldShow(host, text)) return
    show(host, text)
  }, DELAY_MS)
}

function onPointerOut(event: PointerEvent) {
  const host = findHost(event.target)
  if (!host) return
  const next = event.relatedTarget
  if (next instanceof Node && host.contains(next)) return
  if (active === host || showTimer) hide()
}

export function installAppTooltip() {
  document.addEventListener('pointerover', onPointerOver)
  document.addEventListener('pointerout', onPointerOut)
  document.addEventListener('pointerdown', hide, true)
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hide()
  })
  window.addEventListener('scroll', hide, true)
  window.addEventListener('blur', hide)
  window.addEventListener('resize', hide)
}
