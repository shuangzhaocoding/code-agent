import { reactive } from 'vue'

export type ImageLightboxItem = {
  src: string
  alt?: string
  title?: string
}

const state = reactive({
  open: false,
  items: [] as ImageLightboxItem[],
  index: 0,
})

export function openImageLightbox(items: ImageLightboxItem[], index = 0) {
  const list = items.filter((item) => item?.src)
  if (!list.length) return
  state.items = list
  state.index = Math.min(Math.max(0, index), list.length - 1)
  state.open = true
}

export function closeImageLightbox() {
  state.open = false
}

export function useImageLightbox() {
  return {
    state,
    openImageLightbox,
    closeImageLightbox,
  }
}
