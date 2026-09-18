const watches = new WeakMap<HTMLElement, StripWatch>()

const TAB_PAD = 14
const TAB_GAP = 6
const TAB_ICON = 16
const TAB_CLOSE = 22
const TAB_DIRTY = 8
const EXPAND_SLACK = 20

type StripWatch = {
  count: number
  ro: ResizeObserver
  mo: MutationObserver
  update: () => void
  dispose: () => void
}

function isOverflowMenu(el: HTMLElement) {
  return Boolean(el.closest('.dv-tabs-overflow-container'))
}

function findStrip(ptab: HTMLElement): HTMLElement | null {
  if (isOverflowMenu(ptab)) return null
  return ptab.closest('.dv-tabs-container') as HTMLElement | null
}

function availableWidth(strip: HTMLElement) {
  const header = strip.closest('.dv-tabs-and-actions-container') as HTMLElement | null
  if (!header) return strip.clientWidth
  const style = getComputedStyle(header)
  const pad = (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0)
  let extras = 0
  for (const child of Array.from(header.children) as HTMLElement[]) {
    if (child === strip || child.contains(strip)) continue
    extras += child.getBoundingClientRect().width
  }
  return Math.max(0, header.clientWidth - pad - extras)
}

function tabFullWidth(tab: HTMLElement) {
  const ptab = tab.querySelector('.ptab') as HTMLElement | null
  if (!ptab) return Math.ceil(tab.getBoundingClientRect().width)
  const lbl = ptab.querySelector('.lbl') as HTMLElement | null
  const lblW = lbl ? Math.ceil(lbl.scrollWidth) : 0
  const dirtyW = ptab.querySelector('.ptab-dirty') ? TAB_DIRTY : 0
  const parts = [TAB_ICON, lblW, dirtyW, TAB_CLOSE].filter((w) => w > 0)
  return TAB_PAD + parts.reduce((sum, w) => sum + w, 0) + TAB_GAP * Math.max(0, parts.length - 1)
}

function neededWidth(strip: HTMLElement) {
  const tabs = Array.from(strip.querySelectorAll('.dv-tab')) as HTMLElement[]
  if (!tabs.length) return 0
  return tabs.reduce((sum, tab) => sum + tabFullWidth(tab), 0)
}

function createWatch(strip: HTMLElement): StripWatch {
  let compact = strip.classList.contains('ca-tabs-icon-only')
  let raf = 0
  const header = strip.closest('.dv-tabs-and-actions-container') as HTMLElement | null

  const apply = (next: boolean) => {
    if (compact === next) return
    compact = next
    strip.classList.toggle('ca-tabs-icon-only', next)
  }

  const run = () => {
    raf = 0
    if (!strip.isConnected) return
    const tabs = strip.querySelectorAll('.dv-tab')
    if (tabs.length < 2) {
      apply(false)
      return
    }
    const available = availableWidth(strip)
    const needed = neededWidth(strip)
    if (needed > available + 1) apply(true)
    else if (needed <= available - EXPAND_SLACK) apply(false)
  }

  const update = () => {
    if (raf) return
    raf = requestAnimationFrame(run)
  }

  const ro = new ResizeObserver(update)
  ro.observe(strip)
  if (header) ro.observe(header)

  const mo = new MutationObserver(update)
  mo.observe(strip, { childList: true, subtree: true })

  const watch: StripWatch = {
    count: 0,
    ro,
    mo,
    update,
    dispose: () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      mo.disconnect()
      strip.classList.remove('ca-tabs-icon-only')
    },
  }
  update()
  return watch
}

/** Collapse tab labels to icons when the strip cannot fit every title. */
export function watchTabStrip(ptab: HTMLElement): (() => void) | null {
  const strip = findStrip(ptab)
  if (!strip) return null

  let watch = watches.get(strip)
  if (!watch) {
    watch = createWatch(strip)
    watches.set(strip, watch)
  }
  watch.count += 1
  watch.update()

  return () => {
    const current = watches.get(strip)
    if (!current) return
    current.count -= 1
    if (current.count > 0) {
      current.update()
      return
    }
    current.dispose()
    watches.delete(strip)
  }
}
