import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'

export type VirtualRow<T> = {
  item: T
  index: number
}

const NEAR_END_PX = 120
const SIZE_EPSILON_PX = 2

export function useVirtualList<T extends { id: string }>(
  items: Ref<T[]>,
  scrollElement: Ref<HTMLElement | null>,
  options?: {
    threshold?: number
    estimateSize?: number
    overscan?: number
  },
) {
  const threshold = options?.threshold ?? 40
  const estimateSize = options?.estimateSize ?? 168
  const overscan = options?.overscan ?? 6

  const scrollTop = ref(0)
  const viewportHeight = ref(0)
  const sizeMap = ref(new Map<string, number>())
  const observers = new Map<string, ResizeObserver>()

  const enabled = computed(() => items.value.length >= threshold)

  function itemSize(id: string) {
    return sizeMap.value.get(id) ?? estimateSize
  }

  const layout = computed(() => {
    const offsets: number[] = []
    let total = 0
    for (const item of items.value) {
      offsets.push(total)
      total += itemSize(item.id)
    }
    return { offsets, total }
  })

  const range = computed(() => {
    const count = items.value.length
    if (!count) return { start: 0, end: -1 }
    if (!enabled.value) return { start: 0, end: count - 1 }

    const { offsets, total } = layout.value
    const viewTop = scrollTop.value
    const viewBottom = viewTop + Math.max(viewportHeight.value, 1)

    let start = 0
    for (let i = 0; i < count; i += 1) {
      const bottom = offsets[i] + itemSize(items.value[i].id)
      if (bottom >= viewTop) {
        start = Math.max(0, i - overscan)
        break
      }
    }

    let end = count - 1
    for (let i = start; i < count; i += 1) {
      if (offsets[i] > viewBottom) {
        end = Math.min(count - 1, i + overscan)
        break
      }
    }

    // Keep the tail mounted while near/at bottom so streaming growth and
    // pin-to-end do not drop the last message out of the DOM.
    if (viewBottom >= total - NEAR_END_PX) {
      end = count - 1
    }

    return { start, end }
  })

  const visibleItems = computed<VirtualRow<T>[]>(() => {
    const { start, end } = range.value
    if (end < start) return []
    return items.value.slice(start, end + 1).map((item, offset) => ({
      item,
      index: start + offset,
    }))
  })

  const paddingTop = computed(() => {
    if (!enabled.value) return 0
    const idx = range.value.start
    return layout.value.offsets[idx] ?? 0
  })

  const paddingBottom = computed(() => {
    if (!enabled.value) return 0
    const { end } = range.value
    const { offsets, total } = layout.value
    if (end < 0) return 0
    const item = items.value[end]
    if (!item) return 0
    return Math.max(0, total - (offsets[end] ?? 0) - itemSize(item.id))
  })

  function setItemEl(id: string, el: Element | null) {
    const prev = observers.get(id)
    if (prev) {
      prev.disconnect()
      observers.delete(id)
    }
    if (!el || !(el instanceof HTMLElement) || !enabled.value) return

    const measure = () => {
      const height = Math.round(el.getBoundingClientRect().height)
      if (!height) return
      const current = sizeMap.value.get(id)
      // Ignore sub-pixel / 1px churn from fonts/images reflow.
      if (current !== undefined && Math.abs(current - height) < SIZE_EPSILON_PX) return
      const next = new Map(sizeMap.value)
      next.set(id, height)
      sizeMap.value = next
    }

    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    observers.set(id, ro)
  }

  function syncViewportFromEl(el: HTMLElement) {
    scrollTop.value = el.scrollTop
    viewportHeight.value = el.clientHeight
  }

  function onScroll() {
    const el = scrollElement.value
    if (!el) return
    syncViewportFromEl(el)
  }

  /** Move the virtual window to the estimated end without aligning to item tops. */
  function prepareEndWindow() {
    const el = scrollElement.value
    const vh = el?.clientHeight || viewportHeight.value || 1
    viewportHeight.value = vh
    scrollTop.value = Math.max(0, layout.value.total - vh)
  }

  function scrollToIndex(index: number, behavior: ScrollBehavior = 'smooth') {
    const el = scrollElement.value
    if (!el || index < 0 || index >= items.value.length) return
    const top = layout.value.offsets[index] ?? 0
    el.scrollTo({ top, behavior })
    scrollTop.value = top
    viewportHeight.value = el.clientHeight
  }

  /**
   * Scroll to the true container bottom.
   * Must not use scrollToIndex(last): that aligns to the TOP of the last message,
   * which scrolls UP when the last message is taller than the viewport.
   */
  function scrollToEnd(behavior: ScrollBehavior = 'auto') {
    const el = scrollElement.value
    if (!el) return

    if (enabled.value && items.value.length) {
      prepareEndWindow()
    } else {
      viewportHeight.value = el.clientHeight
    }

    const top = Math.max(0, el.scrollHeight - el.clientHeight)
    if (behavior === 'auto') el.scrollTop = top
    else el.scrollTo({ top, behavior })
    syncViewportFromEl(el)
  }

  watch(
    () => items.value.length,
    (len, prev) => {
      if (len < prev) {
        const keep = new Set(items.value.map((item) => item.id))
        const next = new Map<string, number>()
        for (const [id, size] of sizeMap.value.entries()) {
          if (keep.has(id)) next.set(id, size)
        }
        sizeMap.value = next
        for (const id of [...observers.keys()]) {
          if (!keep.has(id)) {
            observers.get(id)?.disconnect()
            observers.delete(id)
          }
        }
      }
    },
  )

  watch(scrollElement, (el, prev) => {
    prev?.removeEventListener('scroll', onScroll)
    el?.addEventListener('scroll', onScroll, { passive: true })
    if (el) syncViewportFromEl(el)
  })

  onBeforeUnmount(() => {
    scrollElement.value?.removeEventListener('scroll', onScroll)
    for (const ro of observers.values()) ro.disconnect()
    observers.clear()
  })

  return {
    enabled,
    visibleItems,
    paddingTop,
    paddingBottom,
    totalHeight: computed(() => layout.value.total),
    setItemEl,
    onScroll,
    prepareEndWindow,
    scrollToIndex,
    scrollToEnd,
  }
}
