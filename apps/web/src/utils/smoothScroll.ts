/** Smooth scroll helpers — use `'auto'` only for high-frequency follow (live streaming). */

const running = new WeakMap<HTMLElement, number>()

function easeOutCubic(t: number) {
  return 1 - (1 - t) ** 3
}

/** Cancel an in-flight animateScrollTo for this element. */
export function cancelSmoothScroll(el: HTMLElement) {
  const id = running.get(el)
  if (id != null) {
    cancelAnimationFrame(id)
    running.delete(el)
  }
}

/**
 * Animate scrollTop with easing. Independent of CSS `scroll-behavior`,
 * so stick-follow can keep using instant `scrollTop` assignments.
 */
export function animateScrollTo(
  el: HTMLElement,
  top: number,
  durationMs = 360,
): Promise<void> {
  cancelSmoothScroll(el)
  const start = el.scrollTop
  const target = Math.max(0, top)
  const delta = target - start
  if (Math.abs(delta) < 1 || durationMs <= 0) {
    el.scrollTop = target
    return Promise.resolve()
  }

  // Cap duration for long distances so the jump still feels snappy.
  const distance = Math.abs(delta)
  const duration = Math.min(durationMs, 220 + Math.sqrt(distance) * 8)
  const t0 = performance.now()

  return new Promise((resolve) => {
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / duration)
      el.scrollTop = start + delta * easeOutCubic(t)
      if (t < 1) {
        running.set(el, requestAnimationFrame(step))
      } else {
        running.delete(el)
        el.scrollTop = target
        resolve()
      }
    }
    running.set(el, requestAnimationFrame(step))
  })
}

export function scrollToTop(
  el: HTMLElement,
  top: number,
  behavior: ScrollBehavior = 'smooth',
) {
  if (behavior === 'smooth') {
    void animateScrollTo(el, top)
    return
  }
  cancelSmoothScroll(el)
  el.scrollTop = Math.max(0, top)
}

export function scrollToBottom(
  el: HTMLElement,
  behavior: ScrollBehavior = 'smooth',
) {
  scrollToTop(el, el.scrollHeight - el.clientHeight, behavior)
}

export function scrollIntoViewSmooth(
  el: Element | null | undefined,
  options?: ScrollIntoViewOptions,
) {
  el?.scrollIntoView({ behavior: 'smooth', block: 'nearest', ...options })
}
