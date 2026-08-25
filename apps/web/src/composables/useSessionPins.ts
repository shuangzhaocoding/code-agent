import { computed, reactive } from 'vue'
import { useAppStore } from '@/stores/app'

const cache = reactive<Record<string, string[]>>({})

function keyFor(workspaceId: string) {
  return `ca.session.pins.${workspaceId}`
}

function read(workspaceId: string): string[] {
  if (!workspaceId) return []
  if (cache[workspaceId]) return cache[workspaceId]
  try {
    const raw = localStorage.getItem(keyFor(workspaceId))
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    cache[workspaceId] = Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'string') : []
  } catch {
    cache[workspaceId] = []
  }
  return cache[workspaceId]
}

function write(workspaceId: string, ids: string[]) {
  cache[workspaceId] = ids
  try {
    localStorage.setItem(keyFor(workspaceId), JSON.stringify(ids))
  } catch {
    /* ignore quota */
  }
}

export function useSessionPins() {
  const store = useAppStore()
  const ids = computed(() => read(store.workspaceId || ''))

  function isPinned(id: string) {
    return ids.value.includes(id)
  }

  function toggle(id: string) {
    const ws = store.workspaceId || ''
    if (!ws) return
    const current = read(ws)
    write(ws, current.includes(id) ? current.filter((x) => x !== id) : [id, ...current])
  }

  function sortByPin<T extends { id: string }>(list: T[]): T[] {
    return [...list].sort((a, b) => {
      const pa = isPinned(a.id) ? 0 : 1
      const pb = isPinned(b.id) ? 0 : 1
      if (pa !== pb) return pa - pb
      if (isPinned(a.id) && isPinned(b.id)) {
        return ids.value.indexOf(a.id) - ids.value.indexOf(b.id)
      }
      return 0
    })
  }

  return { ids, isPinned, toggle, sortByPin }
}
