import { computed, ref } from 'vue'
import { api } from '@/api/http'
import { t } from '@/i18n'

export type BrowseItem = { name: string; path: string; is_dir: boolean }
export type BrowseResult = { path: string; parent: string; items: BrowseItem[] }

function errMessage(err: unknown) {
  const raw = err instanceof Error ? err.message : String(err)
  try {
    const parsed = JSON.parse(raw) as { message?: string }
    if (parsed && typeof parsed.message === 'string') return parsed.message
  } catch {
    /* keep raw */
  }
  return raw
}

export function useWorkspaceBrowse(initial = '~') {
  const browsing = ref<BrowseResult | null>(null)
  const path = ref('')
  const error = ref('')
  const creating = ref(false)
  const createValue = ref('untitled')
  const createKey = ref(0)

  const dirs = computed(() => browsing.value?.items.filter((item) => item.is_dir) || [])

  async function browse(p: string) {
    error.value = ''
    creating.value = false
    browsing.value = await api<BrowseResult>(`/api/workspaces/browse?path=${encodeURIComponent(p)}`)
    path.value = browsing.value?.path || p
  }

  function startCreate() {
    error.value = ''
    createValue.value = ''
    createKey.value += 1
    creating.value = true
  }

  function cancelCreate() {
    creating.value = false
  }

  async function commitCreate() {
    const name = createValue.value.trim()
    if (!name) {
      cancelCreate()
      return
    }
    if (/[\\/]/.test(name) || name === '.' || name === '..') {
      error.value = t('workspace.invalidName')
      return
    }
    const parent = browsing.value?.path || path.value
    if (!parent) return
    try {
      const created = await api<{ path: string }>('/api/workspaces/mkdir', {
        method: 'POST',
        body: JSON.stringify({ parent, name }),
      })
      creating.value = false
      error.value = ''
      await browse(created.path)
    } catch (err) {
      error.value = errMessage(err)
      createKey.value += 1
    }
  }

  return {
    browsing,
    path,
    error,
    creating,
    createValue,
    createKey,
    dirs,
    browse,
    startCreate,
    cancelCreate,
    commitCreate,
    errMessage,
  }
}
