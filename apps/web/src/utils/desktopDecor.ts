import { ref } from 'vue'
import { ApiError } from '@/api/http'

export const BUILTIN_WALLPAPERS = ['none', 'aurora', 'dusk', 'harbor'] as const
export const WALLPAPERS = [...BUILTIN_WALLPAPERS, 'custom'] as const
export type WallpaperId = (typeof WALLPAPERS)[number]

export const BUILTIN_PETS = ['none', 'fox', 'owl', 'bot'] as const
export const PETS = [...BUILTIN_PETS, 'custom'] as const
export type PetId = (typeof PETS)[number]

/** Agent task phases the custom pet can bind to. */
export const PET_TASK_STATUSES = ['idle', 'busy', 'waiting', 'success', 'error'] as const
export type PetTaskStatus = (typeof PET_TASK_STATUSES)[number]

export type CustomWallpaper = {
  id: string
  url: string
  mime?: string
}

export type CustomPetImage = {
  url: string
  mime: string
}

/** One custom pet with per-status images (files live under data_dir/decor). */
export type CustomPet = {
  id: string
  name: string
  images: Partial<Record<PetTaskStatus, CustomPetImage>>
}

const KEYS = {
  wallpaper: 'ca.decor.wallpaper',
  wallpaperActiveId: 'ca.decor.wallpaperActiveId',
  pet: 'ca.decor.pet',
  petPos: 'ca.decor.petPos',
  activeCustomPetId: 'ca.decor.activeCustomPetId',
} as const

/** Hard limit on source file size (bytes) — mirrored by API. */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024

function readId<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (raw && (allowed as readonly string[]).includes(raw)) return raw as T
  } catch {
    /* ignore */
  }
  return fallback
}

function readActiveCustomId(): string {
  try {
    return localStorage.getItem(KEYS.wallpaperActiveId) || ''
  } catch {
    return ''
  }
}

function readActiveCustomPetId(): string {
  try {
    return localStorage.getItem(KEYS.activeCustomPetId) || ''
  } catch {
    return ''
  }
}

const wallpaper = ref<WallpaperId>(readId(KEYS.wallpaper, WALLPAPERS, 'none'))
const customWallpapers = ref<CustomWallpaper[]>([])
const activeCustomId = ref(readActiveCustomId())
const wallpaperImage = ref('')
const pet = ref<PetId>(readId(KEYS.pet, PETS, 'none'))
const customPets = ref<CustomPet[]>([])
const activeCustomPetId = ref(readActiveCustomPetId())
let ready: Promise<void> | null = null

export type PetPos = { x: number; y: number }

export function getPetPosition(): PetPos {
  try {
    const raw = localStorage.getItem(KEYS.petPos)
    if (raw) {
      const parsed = JSON.parse(raw) as PetPos
      if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') return parsed
    }
  } catch {
    /* ignore */
  }
  return { x: 24, y: 24 }
}

export function setPetPosition(pos: PetPos) {
  try {
    localStorage.setItem(KEYS.petPos, JSON.stringify(pos))
  } catch {
    /* ignore */
  }
}

function resolveCustomImage(): string {
  const list = customWallpapers.value
  if (!list.length) return ''
  const hit = list.find((w) => w.id === activeCustomId.value)
  return (hit || list[0]).url || ''
}

function syncWallpaperAttr(id: WallpaperId) {
  if (typeof document === 'undefined') return
  if (id === 'none') document.documentElement.removeAttribute('data-wallpaper')
  else document.documentElement.setAttribute('data-wallpaper', id)
}

function emitWallpaper() {
  wallpaperImage.value = resolveCustomImage()
  window.dispatchEvent(
    new CustomEvent('ca-wallpaper', {
      detail: {
        id: wallpaper.value,
        image: wallpaperImage.value,
        customs: customWallpapers.value.map((w) => ({ id: w.id, url: w.url })),
        activeCustomId: activeCustomId.value,
      },
    }),
  )
}

function persistActiveCustomId(id: string) {
  activeCustomId.value = id
  try {
    if (id) localStorage.setItem(KEYS.wallpaperActiveId, id)
    else localStorage.removeItem(KEYS.wallpaperActiveId)
  } catch {
    /* ignore */
  }
}

function persistActiveCustomPetId(id: string) {
  activeCustomPetId.value = id
  try {
    if (id) localStorage.setItem(KEYS.activeCustomPetId, id)
    else localStorage.removeItem(KEYS.activeCustomPetId)
  } catch {
    /* ignore */
  }
}

function emitPet() {
  window.dispatchEvent(
    new CustomEvent('ca-pet', {
      detail: {
        id: pet.value,
        activeCustomPetId: activeCustomPetId.value,
        customs: customPets.value,
      },
    }),
  )
}

function mapApiError(err: unknown): Error {
  if (err instanceof ApiError) {
    const code = err.code || ''
    if (code.includes('too_large') || code.includes('too-large')) return new Error('too-large')
    if (code.includes('not_image') || code.includes('not-image')) return new Error('not-image')
    if (code.includes('limit')) return new Error('limit')
    if (code.includes('quota') || err.status === 507) return new Error('quota')
    if (err.status === 413) return new Error('too-large')
  }
  if (err instanceof Error) {
    const msg = err.message.toLowerCase()
    if (msg.includes('too_large') || msg.includes('20mb') || msg.includes('exceeds')) return new Error('too-large')
    if (msg.includes('not an image') || msg.includes('not_image')) return new Error('not-image')
    if (msg.includes('limit')) return new Error('limit')
    if (msg.includes('quota')) return new Error('quota')
  }
  return err instanceof Error ? err : new Error('error')
}

async function decorFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    const raw = await res.text()
    let detail: unknown = raw
    try {
      detail = raw ? JSON.parse(raw) : raw
    } catch {
      detail = raw
    }
    throw new ApiError(res.status, detail, res.statusText)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export function currentWallpaper(): WallpaperId {
  return wallpaper.value
}

export function currentWallpaperImage(): string {
  return wallpaperImage.value || resolveCustomImage()
}

export function currentPet(): PetId {
  return pet.value
}

/** True when a wallpaper (builtin or custom) is active on <html>. */
export function hasActiveWallpaper(): boolean {
  if (typeof document === 'undefined') return false
  return document.documentElement.hasAttribute('data-wallpaper')
}

/**
 * Opaque-or-glass fill for canvas widgets (Monaco / xterm) that cannot use CSS color-mix.
 * Returns #RRGGBB or #RRGGBBAA.
 */
export function decorGlassHex(kind: 'editor' | 'terminal' | 'panel' = 'panel'): string {
  const dark =
    typeof document !== 'undefined' &&
    document.documentElement.getAttribute('data-theme') === 'dark'
  const r = dark ? 18 : 255
  const g = dark ? 18 : 255
  const b = dark ? 24 : 255
  const hex = (n: number) => n.toString(16).padStart(2, '0')
  const rgb = `#${hex(r)}${hex(g)}${hex(b)}`
  if (!hasActiveWallpaper()) return rgb
  const alpha =
    kind === 'editor' ? 0.4 : kind === 'terminal' ? 0.38 : 0.36
  const aa = Math.round(alpha * 255).toString(16).padStart(2, '0')
  return `${rgb}${aa}`
}

/** rgba() form for xterm / CSS that prefer functional notation. */
export function decorGlassRgba(kind: 'editor' | 'terminal' | 'panel' = 'panel'): string {
  const dark =
    typeof document !== 'undefined' &&
    document.documentElement.getAttribute('data-theme') === 'dark'
  const rgb = dark ? '18, 18, 24' : '255, 255, 255'
  if (!hasActiveWallpaper()) return dark ? 'rgb(18, 18, 24)' : 'rgb(255, 255, 255)'
  const alpha =
    kind === 'editor' ? 0.4 : kind === 'terminal' ? 0.38 : 0.36
  return `rgba(${rgb}, ${alpha})`
}

export function setWallpaper(id: WallpaperId) {
  if (id === 'custom' && !resolveCustomImage()) return
  wallpaper.value = id
  try {
    localStorage.setItem(KEYS.wallpaper, id)
  } catch {
    /* ignore */
  }
  syncWallpaperAttr(id)
  emitWallpaper()
}

export function selectCustomWallpaper(id: string) {
  const hit = customWallpapers.value.find((w) => w.id === id)
  if (!hit) return
  persistActiveCustomId(id)
  setWallpaper('custom')
}

export async function removeCustomWallpaper(id: string) {
  try {
    await decorFetch(`/api/decor/wallpapers/${encodeURIComponent(id)}`, { method: 'DELETE' })
  } catch (err) {
    throw mapApiError(err)
  }
  customWallpapers.value = customWallpapers.value.filter((w) => w.id !== id)
  if (activeCustomId.value === id) {
    const next = customWallpapers.value[0]?.id || ''
    persistActiveCustomId(next)
    if (!next && wallpaper.value === 'custom') setWallpaper('none')
    else emitWallpaper()
  } else {
    emitWallpaper()
  }
}

export async function addCustomWallpaperFromFile(file: File) {
  if (!file.type.startsWith('image/')) throw new Error('not-image')
  if (file.size > MAX_UPLOAD_BYTES) throw new Error('too-large')
  const body = new FormData()
  body.append('file', file)
  try {
    const item = await decorFetch<CustomWallpaper>('/api/decor/wallpapers', {
      method: 'POST',
      body,
    })
    customWallpapers.value = [...customWallpapers.value, item]
    persistActiveCustomId(item.id)
    setWallpaper('custom')
    return item
  } catch (err) {
    throw mapApiError(err)
  }
}

export async function replaceCustomWallpaperFromFile(id: string, file: File) {
  if (!file.type.startsWith('image/')) throw new Error('not-image')
  if (file.size > MAX_UPLOAD_BYTES) throw new Error('too-large')
  const body = new FormData()
  body.append('file', file)
  try {
    const item = await decorFetch<CustomWallpaper>(
      `/api/decor/wallpapers/${encodeURIComponent(id)}`,
      { method: 'PUT', body },
    )
    customWallpapers.value = customWallpapers.value.map((w) => (w.id === id ? item : w))
    persistActiveCustomId(id)
    setWallpaper('custom')
    return item
  } catch (err) {
    throw mapApiError(err)
  }
}

/** @deprecated use addCustomWallpaperFromFile */
export async function setCustomWallpaperFromFile(file: File) {
  return addCustomWallpaperFromFile(file)
}

export function clearCustomWallpaper() {
  void (async () => {
    const ids = customWallpapers.value.map((w) => w.id)
    for (const id of ids) {
      try {
        await removeCustomWallpaper(id)
      } catch {
        /* ignore */
      }
    }
  })()
}

export function setPet(id: PetId) {
  if (id === 'custom' && !customPets.value.length) return
  pet.value = id
  try {
    localStorage.setItem(KEYS.pet, id)
  } catch {
    /* ignore */
  }
  if (id === 'custom' && !activeCustomPetId.value && customPets.value[0]) {
    persistActiveCustomPetId(customPets.value[0].id)
  }
  emitPet()
}

export function selectCustomPet(id: string) {
  const hit = customPets.value.find((p) => p.id === id)
  if (!hit) return
  persistActiveCustomPetId(id)
  setPet('custom')
}

export async function createCustomPet(name?: string) {
  const body = new FormData()
  if (name?.trim()) body.append('name', name.trim())
  try {
    const item = await decorFetch<CustomPet>('/api/decor/pets', { method: 'POST', body })
    customPets.value = [...customPets.value, item]
    persistActiveCustomPetId(item.id)
    setPet('custom')
    return item
  } catch (err) {
    throw mapApiError(err)
  }
}

export async function renameCustomPet(id: string, name: string) {
  const body = new FormData()
  body.append('name', name.trim() || 'Pet')
  try {
    const next = await decorFetch<CustomPet>(`/api/decor/pets/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body,
    })
    customPets.value = customPets.value.map((p) => (p.id === id ? next : p))
    emitPet()
  } catch (err) {
    throw mapApiError(err)
  }
}

export async function setCustomPetStatusImage(petId: string, status: PetTaskStatus, file: File) {
  if (!file.type.startsWith('image/')) throw new Error('not-image')
  if (file.size > MAX_UPLOAD_BYTES) throw new Error('too-large')
  const body = new FormData()
  body.append('file', file)
  try {
    const next = await decorFetch<CustomPet>(
      `/api/decor/pets/${encodeURIComponent(petId)}/images/${encodeURIComponent(status)}`,
      { method: 'POST', body },
    )
    customPets.value = customPets.value.map((p) => (p.id === petId ? next : p))
    persistActiveCustomPetId(petId)
    setPet('custom')
  } catch (err) {
    throw mapApiError(err)
  }
}

export async function clearCustomPetStatusImage(petId: string, status: PetTaskStatus) {
  try {
    const next = await decorFetch<CustomPet>(
      `/api/decor/pets/${encodeURIComponent(petId)}/images/${encodeURIComponent(status)}`,
      { method: 'DELETE' },
    )
    customPets.value = customPets.value.map((p) => (p.id === petId ? next : p))
    emitPet()
  } catch (err) {
    throw mapApiError(err)
  }
}

export async function removeCustomPet(id: string) {
  try {
    await decorFetch(`/api/decor/pets/${encodeURIComponent(id)}`, { method: 'DELETE' })
  } catch (err) {
    throw mapApiError(err)
  }
  customPets.value = customPets.value.filter((p) => p.id !== id)
  if (activeCustomPetId.value === id) {
    const next = customPets.value[0]?.id || ''
    persistActiveCustomPetId(next)
  }
  if (!customPets.value.length && pet.value === 'custom') setPet('none')
  else emitPet()
}

/** @deprecated */
export async function addCustomPetFromFile(file: File, status: PetTaskStatus = 'idle') {
  let target = customPets.value.find((p) => p.id === activeCustomPetId.value)
  if (!target) target = await createCustomPet()
  await setCustomPetStatusImage(target.id, status, file)
  return target
}

/** Map live agent run → pet task status. */
export function resolvePetTaskStatus(input: {
  runStatus: string
  isBusy: boolean
  awaitingApproval?: boolean
}): PetTaskStatus {
  if (input.awaitingApproval) return 'waiting'
  if (input.isBusy) return 'busy'
  const s = (input.runStatus || 'idle').toLowerCase()
  if (s === 'completed' || s === 'success') return 'success'
  if (s === 'failed' || s === 'error' || s === 'cancelled') return 'error'
  return 'idle'
}

export function activeCustomPet(): CustomPet | null {
  if (!customPets.value.length) return null
  return (
    customPets.value.find((p) => p.id === activeCustomPetId.value) ||
    customPets.value[0] ||
    null
  )
}

/** Pick the best image on a pet profile for a task status. */
export function pickCustomPetImage(
  status: PetTaskStatus,
  profile: CustomPet | null = activeCustomPet(),
): CustomPetImage | null {
  if (!profile) return null
  return (
    profile.images[status] ||
    profile.images.idle ||
    PET_TASK_STATUSES.map((s) => profile.images[s]).find(Boolean) ||
    null
  )
}

/** @deprecated */
export function pickCustomPetForStatus(
  status: PetTaskStatus,
): { id: string; url: string; mime: string; status: PetTaskStatus } | null {
  const profile = activeCustomPet()
  const img = pickCustomPetImage(status, profile)
  if (!profile || !img) return null
  return { id: profile.id, url: img.url, mime: img.mime, status }
}

async function loadFromServer() {
  const data = await decorFetch<{
    wallpapers: CustomWallpaper[]
    pets: CustomPet[]
  }>('/api/decor')
  customWallpapers.value = Array.isArray(data.wallpapers) ? data.wallpapers : []
  customPets.value = Array.isArray(data.pets) ? data.pets : []
}

export function initDesktopDecor() {
  if (!ready) {
    ready = (async () => {
      try {
        await loadFromServer()
      } catch {
        customWallpapers.value = []
        customPets.value = []
      }
      wallpaperImage.value = resolveCustomImage()
      if (activeCustomId.value && !customWallpapers.value.some((w) => w.id === activeCustomId.value)) {
        persistActiveCustomId(customWallpapers.value[0]?.id || '')
      }
      if (
        activeCustomPetId.value &&
        !customPets.value.some((p) => p.id === activeCustomPetId.value)
      ) {
        persistActiveCustomPetId(customPets.value[0]?.id || '')
      } else if (!activeCustomPetId.value && customPets.value[0]) {
        persistActiveCustomPetId(customPets.value[0].id)
      }
      let id = readId(KEYS.wallpaper, WALLPAPERS, 'none')
      if (id === 'custom' && !resolveCustomImage()) id = 'none'
      wallpaper.value = id
      let petId = readId(KEYS.pet, PETS, 'none')
      if (petId === 'custom' && !customPets.value.length) petId = 'none'
      pet.value = petId
      syncWallpaperAttr(wallpaper.value)
      emitWallpaper()
      emitPet()
    })()
  }
  return ready
}

export function useDesktopDecor() {
  return {
    wallpaper,
    wallpaperImage,
    customWallpapers,
    activeCustomId,
    pet,
    customPets,
    activeCustomPetId,
    setWallpaper,
    selectCustomWallpaper,
    addCustomWallpaperFromFile,
    replaceCustomWallpaperFromFile,
    setCustomWallpaperFromFile,
    removeCustomWallpaper,
    clearCustomWallpaper,
    setPet,
    selectCustomPet,
    createCustomPet,
    renameCustomPet,
    setCustomPetStatusImage,
    clearCustomPetStatusImage,
    removeCustomPet,
    addCustomPetFromFile,
    pickCustomPetImage,
    pickCustomPetForStatus,
    activeCustomPet,
    resolvePetTaskStatus,
  }
}
