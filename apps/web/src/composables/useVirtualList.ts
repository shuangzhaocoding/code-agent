import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'

export type VirtualRow<T> = {
  item: T
  index: number
}

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

    const { offsets } = layout.value
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
      const height = Math.ceil(el.getBoundingClientRect().height)
      if (!height) return
      const current = sizeMap.value.get(id)
      if (current === height) return
      const next = new Map(sizeMap.value)
      next.set(id, height)
      sizeMap.value = next
    }

    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    observers.set(id, ro)
  }

  function onScroll() {
    const el = scrollElement.value
    if (!el) return
    scrollTop.value = el.scrollTop
    viewportHeight.value = el.clientHeight
  }

  function scrollToIndex(index: number, behavior: ScrollBehavior = 'smooth') {
    const el = scrollElement.value
    if (!el || index < 0 || index >= items.value.length) return
    const top = layout.value.offsets[index] ?? 0
    el.scrollTo({ top, behavior })
    scrollTop.value = top
    viewportHeight.value = el.clientHeight
  }

  function scrollToEnd(behavior: ScrollBehavior = 'auto') {
    const el = scrollElement.value
    if (!el) return
    if (enabled.value && items.value.length) {
      scrollToIndex(items.value.length - 1, 'auto')
    }
    const top = Math.max(0, el.scrollHeight - el.clientHeight)
    el.scrollTo({ top, behavior })
    scrollTop.value = el.scrollTop
    viewportHeight.value = el.clientHeight
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
    if (el) {
      viewportHeight.value = el.clientHeight
      scrollTop.value = el.scrollTop
    }
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
    scrollToIndex,
    scrollToEnd,
  }
}
