import { ref } from 'vue'

export const BRAND_MARKS = ['atom', 'ca', 'brackets', 'cursor', 'hex'] as const

export type BrandMarkId = (typeof BRAND_MARKS)[number]

const KEY = 'ca.brand.mark'

export function isBrandMarkId(value: string): value is BrandMarkId {
  return (BRAND_MARKS as readonly string[]).includes(value)
}

function readStored(): BrandMarkId {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved && isBrandMarkId(saved)) return saved
  } catch {
    /* ignore */
  }
  return 'atom'
}

const brandMark = ref<BrandMarkId>(readStored())

export function currentBrandMark(): BrandMarkId {
  return brandMark.value
}

export function applyBrandFavicon(id: BrandMarkId = brandMark.value) {
  if (typeof document === 'undefined') return
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  link.type = 'image/svg+xml'
  link.href = `/brand/${id}.svg`
}

export function setBrandMark(id: BrandMarkId) {
  brandMark.value = id
  try {
    localStorage.setItem(KEY, id)
  } catch {
    /* ignore */
  }
  applyBrandFavicon(id)
  window.dispatchEvent(new CustomEvent('ca-brand-mark', { detail: id }))
}

export function initBrandMark() {
  brandMark.value = readStored()
  applyBrandFavicon(brandMark.value)
}

export function useBrandMark() {
  return { brandMark, setBrandMark }
}
