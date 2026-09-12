import { computed, ref } from 'vue'
import { isHttpUrl, safeExternalUrl } from '@/utils/openUrl'

export type UrlPreviewTab = {
  id: string
  url: string
  title: string
  frameKey: number
  blocked: boolean
}

const tabs = ref<UrlPreviewTab[]>([])
const activeId = ref<string | null>(null)

function newTabId() {
  return `url-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function previewTitleFromUrl(url: string) {
  if (!url) return ''
  try {
    const parsed = new URL(url)
    const path = parsed.pathname === '/' ? '' : parsed.pathname
    return `${parsed.hostname}${path}${parsed.search}`.replace(/\/$/, '') || parsed.hostname || url
  } catch {
    return url
  }
}

export function resolvePreviewUrl(raw: string): string | null {
  const trimmed = (raw || '').trim()
  if (!trimmed) return null
  const withProto = /^(https?:|mailto:)/i.test(trimmed) ? trimmed : `https://${trimmed}`
  return safeExternalUrl(withProto)
}

function emitOpenPanel() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('ca-open-url-preview'))
}

export function openUrlPreview(raw: string) {
  const url = resolvePreviewUrl(raw)
  if (!url || !isHttpUrl(url)) return null
  const existing = tabs.value.find((tab) => tab.url === url)
  if (existing) {
    activeId.value = existing.id
    emitOpenPanel()
    return existing
  }
  const tab: UrlPreviewTab = {
    id: newTabId(),
    url,
    title: previewTitleFromUrl(url),
    frameKey: 0,
    blocked: false,
  }
  tabs.value.push(tab)
  activeId.value = tab.id
  emitOpenPanel()
  return tab
}

export function addBlankPreviewTab() {
  const tab: UrlPreviewTab = {
    id: newTabId(),
    url: '',
    title: '',
    frameKey: 0,
    blocked: false,
  }
  tabs.value.push(tab)
  activeId.value = tab.id
  emitOpenPanel()
  return tab
}

export function activatePreviewTab(id: string) {
  if (tabs.value.some((tab) => tab.id === id)) activeId.value = id
}

export function closePreviewTab(id: string) {
  const index = tabs.value.findIndex((tab) => tab.id === id)
  if (index < 0) return
  tabs.value.splice(index, 1)
  if (activeId.value === id) {
    const next = tabs.value[index] || tabs.value[index - 1] || null
    activeId.value = next?.id || null
  }
}

export function navigatePreviewTab(id: string, raw: string) {
  const tab = tabs.value.find((row) => row.id === id)
  const url = resolvePreviewUrl(raw)
  if (!tab || !url || !isHttpUrl(url)) return false
  const dup = tabs.value.find((row) => row.id !== id && row.url === url)
  if (dup) {
    closePreviewTab(id)
    activeId.value = dup.id
    return true
  }
  tab.url = url
  tab.title = previewTitleFromUrl(url)
  tab.frameKey += 1
  tab.blocked = false
  return true
}

export function reloadPreviewTab(id: string) {
  const tab = tabs.value.find((row) => row.id === id)
  if (!tab?.url) return
  tab.frameKey += 1
  tab.blocked = false
}

export function markPreviewTabBlocked(id: string) {
  const tab = tabs.value.find((row) => row.id === id)
  if (tab) tab.blocked = true
}

export function useUrlPreview() {
  const activeTab = computed(() => tabs.value.find((tab) => tab.id === activeId.value) || null)
  return {
    tabs,
    activeId,
    activeTab,
    openUrlPreview,
    addBlankPreviewTab,
    activatePreviewTab,
    closePreviewTab,
    navigatePreviewTab,
    reloadPreviewTab,
    markPreviewTabBlocked,
  }
}
