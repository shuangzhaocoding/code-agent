import { createI18n } from 'vue-i18n'
import zh from './locales/zh.json'
import en from './locales/en.json'
import ja from './locales/ja.json'
import ko from './locales/ko.json'
import de from './locales/de.json'

export const LOCALE_KEY = 'ca.locale'

export const SUPPORTED_LOCALES = [
  { id: 'zh', htmlLang: 'zh-CN', bcp47: 'zh-CN' },
  { id: 'en', htmlLang: 'en', bcp47: 'en' },
  { id: 'ja', htmlLang: 'ja', bcp47: 'ja-JP' },
  { id: 'ko', htmlLang: 'ko', bcp47: 'ko-KR' },
  { id: 'de', htmlLang: 'de', bcp47: 'de-DE' },
] as const

export type LocaleId = (typeof SUPPORTED_LOCALES)[number]['id']

const messages = { zh, en, ja, ko, de }

export function isLocaleId(value: string): value is LocaleId {
  return SUPPORTED_LOCALES.some((item) => item.id === value)
}

export function detectLocale(): LocaleId {
  try {
    const saved = localStorage.getItem(LOCALE_KEY)
    if (saved && isLocaleId(saved)) return saved
  } catch {
    /* ignore */
  }
  const nav = (navigator.language || '').toLowerCase()
  if (nav.startsWith('zh')) return 'zh'
  if (nav.startsWith('ja')) return 'ja'
  if (nav.startsWith('ko')) return 'ko'
  if (nav.startsWith('de')) return 'de'
  if (nav.startsWith('en')) return 'en'
  return 'zh'
}

export function localeMeta(id: LocaleId = currentLocale()) {
  return SUPPORTED_LOCALES.find((item) => item.id === id) || SUPPORTED_LOCALES[0]
}

export function applyDocumentLang(id: LocaleId) {
  const meta = localeMeta(id)
  document.documentElement.lang = meta.htmlLang
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'zh',
  messages,
  missingWarn: false,
  fallbackWarn: false,
})

export function currentLocale(): LocaleId {
  const value = String(i18n.global.locale.value)
  return isLocaleId(value) ? value : 'zh'
}

export function t(key: string, params?: Record<string, unknown>) {
  return i18n.global.t(key, params as Record<string, string>) as string
}

export function te(key: string) {
  return i18n.global.te(key)
}

export function panelTitle(id: string) {
  const key = `panels.${id}`
  return te(key) ? t(key) : id
}

export function setLocale(id: LocaleId) {
  i18n.global.locale.value = id
  try {
    localStorage.setItem(LOCALE_KEY, id)
  } catch {
    /* ignore */
  }
  applyDocumentLang(id)
  window.dispatchEvent(new CustomEvent('ca-locale', { detail: id }))
}

applyDocumentLang(currentLocale())
