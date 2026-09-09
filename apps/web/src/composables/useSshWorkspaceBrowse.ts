import { computed, ref } from 'vue'
import { api } from '@/api/http'
import { t } from '@/i18n'
import type { BrowseItem, BrowseResult } from '@/composables/useWorkspaceBrowse'

export type SshAuthForm = {
  display_name: string
  host: string
  port: number
  username: string
  password: string
  private_key: string
  passphrase: string
}

export function useSshWorkspaceBrowse() {
  const browsing = ref<BrowseResult | null>(null)
  const path = ref('~')
  const error = ref('')
  const connecting = ref(false)
  const reuseFromWorkspaceId = ref<string | null>(null)
  const auth = ref<SshAuthForm>({
    display_name: '',
    host: '',
    port: 22,
    username: '',
    password: '',
    private_key: '',
    passphrase: '',
  })

  const dirs = computed(() => browsing.value?.items.filter((item) => item.is_dir) || [])
  const atRoots = computed(() => browsing.value != null && browsing.value.path === '' && browsing.value.parent === '')
  const canGoParent = computed(() => browsing.value != null && !atRoots.value)
  const displayPath = computed(() => {
    if (!browsing.value) return ''
    if (atRoots.value) return t('workspace.rootsLabel')
    return browsing.value.path
  })
  const reusingCredentials = computed(() => Boolean(reuseFromWorkspaceId.value))

  function errMessage(err: unknown) {
    const raw = err instanceof Error ? err.message : String(err)
    try {
      const parsed = JSON.parse(raw) as { message?: string }
      if (parsed && typeof parsed.message === 'string') return parsed.message
    } catch {
      /* keep */
    }
    return raw
  }

  async function browse(p: string) {
    error.value = ''
    connecting.value = true
    try {
      const body: Record<string, unknown> = {
        host: auth.value.host.trim(),
        port: Number(auth.value.port) || 22,
        username: auth.value.username.trim(),
        path: p,
      }
      if (reuseFromWorkspaceId.value) {
        body.workspace_id = reuseFromWorkspaceId.value
      }
      if (auth.value.password) body.password = auth.value.password
      if (auth.value.private_key) {
        body.private_key = auth.value.private_key
        body.passphrase = auth.value.passphrase || null
      }
      browsing.value = await api<BrowseResult>('/api/workspaces/ssh/browse', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      path.value = browsing.value?.path || p
    } catch (err) {
      error.value = errMessage(err)
      throw err
    } finally {
      connecting.value = false
    }
  }

  function goParent() {
    if (!canGoParent.value || !browsing.value) return
    void browse(browsing.value.parent || '')
  }

  return {
    auth,
    browsing,
    path,
    error,
    connecting,
    reuseFromWorkspaceId,
    reusingCredentials,
    dirs,
    atRoots,
    canGoParent,
    displayPath,
    browse,
    goParent,
    errMessage,
  }
}

export type { BrowseItem }
