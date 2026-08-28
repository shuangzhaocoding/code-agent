/** Smooth scroll helpers — use `'auto'` only for high-frequency follow (live streaming). */

export function scrollToTop(
  el: HTMLElement,
  top: number,
  behavior: ScrollBehavior = 'smooth',
) {
  el.scrollTo({ top: Math.max(0, top), behavior })
}

export function scrollToBottom(
  el: HTMLElement,
  behavior: ScrollBehavior = 'smooth',
) {
  scrollToTop(el, el.scrollHeight, behavior)
}

export function scrollIntoViewSmooth(
  el: Element | null | undefined,
  options?: ScrollIntoViewOptions,
) {
  el?.scrollIntoView({ behavior: 'smooth', block: 'nearest', ...options })
}
