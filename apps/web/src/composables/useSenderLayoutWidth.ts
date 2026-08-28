import { inject, provide, ref, watch, type InjectionKey, type Ref } from 'vue'

export type SenderFooterLayout = {
  footerWidth: Ref<number>
  footerLeftWidth: Ref<number>
  footerRightWidth: Ref<number>
}

export const senderFooterLayoutKey: InjectionKey<SenderFooterLayout> = Symbol('senderFooterLayout')

/** @deprecated use senderFooterLayoutKey.footerWidth */
export const senderLayoutWidthKey: InjectionKey<Ref<number>> = Symbol('senderLayoutWidth')

export function provideSenderFooterLayout(container: Ref<HTMLElement | null | undefined>) {
  const footerWidth = ref(Number.POSITIVE_INFINITY)
  const footerLeftWidth = ref(Number.POSITIVE_INFINITY)
  const footerRightWidth = ref(Number.POSITIVE_INFINITY)

  let observer: ResizeObserver | null = null

  watch(
    container,
    (el, _, onCleanup) => {
      observer?.disconnect()
      observer = null
      if (!el) return

      const update = () => {
        footerWidth.value = el.getBoundingClientRect().width
        const footer = el.querySelector('.tr-sender-footer')
        const left = footer?.querySelector('.tr-sender-footer-left')
        const right = footer?.querySelector('.tr-sender-footer-right')
        footerLeftWidth.value = left?.getBoundingClientRect().width ?? footerWidth.value
        footerRightWidth.value = right?.getBoundingClientRect().width ?? 0
      }

      update()
      observer = new ResizeObserver(update)
      observer.observe(el)
      const observed = new Set<Element>()
      const observeFooter = () => {
        const footer = el.querySelector('.tr-sender-footer')
        if (!footer || !observer) return
        for (const node of [footer, ...footer.querySelectorAll('.tr-sender-footer-left, .tr-sender-footer-right')]) {
          if (!observed.has(node)) {
            observer.observe(node)
            observed.add(node)
          }
        }
      }
      observeFooter()
      const mutation = new MutationObserver(() => {
        update()
        observeFooter()
      })
      mutation.observe(el, { childList: true, subtree: true })
      onCleanup(() => {
        mutation.disconnect()
        observer?.disconnect()
        observed.clear()
      })
    },
    { immediate: true },
  )

  const layout: SenderFooterLayout = { footerWidth, footerLeftWidth, footerRightWidth }
  provide(senderFooterLayoutKey, layout)
  provide(senderLayoutWidthKey, footerWidth)
  return layout
}

/** @deprecated use provideSenderFooterLayout */
export function provideSenderLayoutWidth(container: Ref<HTMLElement | null | undefined>) {
  return provideSenderFooterLayout(container)
}

export function useSenderFooterLayout(): SenderFooterLayout {
  const fallback = ref(Number.POSITIVE_INFINITY)
  return (
    inject(senderFooterLayoutKey, {
      footerWidth: fallback,
      footerLeftWidth: fallback,
      footerRightWidth: fallback,
    }) ?? {
      footerWidth: fallback,
      footerLeftWidth: fallback,
      footerRightWidth: fallback,
    }
  )
}

export function useSenderLayoutWidth() {
  return useSenderFooterLayout().footerWidth
}
