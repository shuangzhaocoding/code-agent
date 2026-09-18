<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import FormSelect from '@/components/FormSelect.vue'
import LanguageSelect from '@/components/LanguageSelect.vue'
import LayoutControls from '@/components/LayoutControls.vue'
import BrandMark from '@/components/BrandMark.vue'
import ImageCropDialog, { type CropKind } from '@/components/ImageCropDialog.vue'
import { useToast } from '@/composables/useToast'
import { useGitDiffTarget } from '@/composables/useGitDiffTarget'
import { BRAND_MARKS, useBrandMark } from '@/utils/brandMark'
import {
  BUILTIN_PETS,
  BUILTIN_WALLPAPERS,
  PET_TASK_STATUSES,
  useDesktopDecor,
  type PetTaskStatus,
  type WallpaperId,
} from '@/utils/desktopDecor'
import { getPortsNotifyNew, setPortsNotifyNew } from '@/composables/usePortsWatch'
import {
  getEditorThemeId,
  listEditorThemeOptions,
  setEditorThemeId,
} from '@/utils/editorTheme'
import { api } from '@/api/http'
import { getDesktopBridge } from '@/utils/desktop'

type PythonInterpreterItem = {
  path: string
  label: string
  version?: string | null
  kind?: string
}

type SchemaSpec = {
  title?: string
  enum?: string[]
  format?: string
  type?: string
  minimum?: number
  maximum?: number
  default?: unknown
  requires_restart?: boolean
  example?: string
  scope?: 'user' | 'workspace' | string
}

defineOptions({ inheritAttrs: false })
defineProps<{
  params?: unknown
  api?: unknown
  containerApi?: unknown
  tabLocation?: string
}>()

const { t, te } = useI18n()
const store = useAppStore()
const toast = useToast()
const { diffTarget, setDiffTarget } = useGitDiffTarget()
const { brandMark, setBrandMark } = useBrandMark()
const portsNotifyNew = ref(getPortsNotifyNew())
const editorThemeId = ref(getEditorThemeId())
const editorThemeOptions = computed(() =>
  listEditorThemeOptions(t('settings.editorThemeAuto')).map((o) => ({
    value: o.id,
    label: o.label,
  })),
)
const settingsScope = ref<'user' | 'workspace'>('user')
const localWorkspace = reactive<Record<string, unknown>>({})
const baselineWorkspace = ref<Record<string, unknown>>({})
const pythonInterpreters = ref<PythonInterpreterItem[]>([])
const pythonInterpretersLoading = ref(false)

function onPortsNotifyToggle(enabled: boolean) {
  portsNotifyNew.value = enabled
  setPortsNotifyNew(enabled)
}

function onEditorThemeChange(id: string) {
  editorThemeId.value = setEditorThemeId(id)
}
const {
  wallpaper,
  customWallpapers,
  activeCustomId,
  pet,
  customPets,
  activeCustomPetId,
  setWallpaper,
  selectCustomWallpaper,
  addCustomWallpaperFromFile,
  replaceCustomWallpaperFromFile,
  removeCustomWallpaper,
  setPet,
  selectCustomPet,
  createCustomPet,
  renameCustomPet,
  setCustomPetStatusImage,
  clearCustomPetStatusImage,
  removeCustomPet,
  pickCustomPetImage,
  activeCustomPet,
} = useDesktopDecor()
const wallpaperFileInput = ref<HTMLInputElement | null>(null)
const wallpaperUploading = ref(false)
const petStatusFileInput = ref<HTMLInputElement | null>(null)
const petUploading = ref(false)
const petUploadStatus = ref<PetTaskStatus>('idle')
const editingPetId = ref('')
const cropOpen = ref(false)
const cropKind = ref<CropKind>('wallpaper')
const cropMode = ref<'upload' | 'edit'>('upload')
const cropFile = ref<File | null>(null)
const cropSrcUrl = ref<string | null>(null)
const cropQueue = ref<File[]>([])
const cropReplaceWallpaperId = ref('')
const cropReplacePetStatus = ref<PetTaskStatus | null>(null)
const local = reactive<Record<string, unknown>>({})
const baseline = ref<Record<string, unknown>>({})
const saved = ref(false)
const saving = ref(false)
const activeGroup = ref('appearance')

const editingPet = computed(
  () =>
    customPets.value.find((p) => p.id === editingPetId.value) ||
    activeCustomPet() ||
    customPets.value[0] ||
    null,
)

watch(
  [customPets, activeCustomPetId],
  () => {
    if (!editingPetId.value || !customPets.value.some((p) => p.id === editingPetId.value)) {
      editingPetId.value = activeCustomPetId.value || customPets.value[0]?.id || ''
    }
  },
  { immediate: true },
)

function isAnimatedMime(mime?: string | null) {
  const m = (mime || '').toLowerCase()
  return m === 'image/gif' || m === 'image/apng' || m.includes('gif')
}

function isAnimatedImage(file: File) {
  return isAnimatedMime(file.type)
}

function canRecropMime(mime?: string | null) {
  return Boolean(mime) ? !isAnimatedMime(mime) : true
}

function openCrop(kind: CropKind, files: File[]) {
  const list = files.filter(Boolean)
  if (!list.length) return
  cropKind.value = kind
  cropMode.value = 'upload'
  cropSrcUrl.value = null
  cropReplaceWallpaperId.value = ''
  cropReplacePetStatus.value = null
  cropQueue.value = list.slice(1)
  const first = list[0]
  if (isAnimatedImage(first)) {
    void uploadCropped(kind, first)
    if (cropQueue.value.length) openCrop(kind, cropQueue.value)
    return
  }
  cropFile.value = first
  cropOpen.value = true
}

function openRecropWallpaper(id: string, url: string, mime?: string) {
  if (!canRecropMime(mime)) {
    toast.info(t('desktopDecor.crop.animatedSkip'))
    return
  }
  cropKind.value = 'wallpaper'
  cropMode.value = 'edit'
  cropFile.value = null
  cropSrcUrl.value = url
  cropQueue.value = []
  cropReplaceWallpaperId.value = id
  cropReplacePetStatus.value = null
  cropOpen.value = true
}

function openRecropPetStatus(status: PetTaskStatus) {
  const img = editingPet.value?.images[status]
  if (!img?.url) return
  if (!canRecropMime(img.mime)) {
    toast.info(t('desktopDecor.crop.animatedSkip'))
    return
  }
  cropKind.value = 'pet'
  cropMode.value = 'edit'
  cropFile.value = null
  cropSrcUrl.value = img.url
  cropQueue.value = []
  cropReplaceWallpaperId.value = ''
  cropReplacePetStatus.value = status
  petUploadStatus.value = status
  cropOpen.value = true
}

function closeCrop() {
  cropOpen.value = false
  cropFile.value = null
  cropSrcUrl.value = null
  cropQueue.value = []
  cropReplaceWallpaperId.value = ''
  cropReplacePetStatus.value = null
  cropMode.value = 'upload'
}

async function uploadCropped(kind: CropKind, file: File) {
  if (kind === 'wallpaper') {
    wallpaperUploading.value = true
    try {
      const replaceId = cropReplaceWallpaperId.value
      if (replaceId) {
        await replaceCustomWallpaperFromFile(replaceId, file)
        toast.success(t('desktopDecor.crop.saveOk'))
      } else {
        await addCustomWallpaperFromFile(file)
        toast.success(t('desktopDecor.uploadOk'))
      }
    } catch (err) {
      const code = err instanceof Error ? err.message : 'error'
      const key =
        code === 'not-image'
          ? 'desktopDecor.uploadNotImage'
          : code === 'limit'
            ? 'desktopDecor.uploadLimit'
            : code === 'too-large'
              ? 'desktopDecor.uploadTooLarge'
              : code === 'quota'
                ? 'desktopDecor.uploadQuota'
                : 'desktopDecor.uploadFail'
      toast.error(t(key))
    } finally {
      wallpaperUploading.value = false
    }
    return
  }
  const targetId = editingPet.value?.id
  if (!targetId) return
  petUploading.value = true
  try {
    const status = cropReplacePetStatus.value || petUploadStatus.value
    await setCustomPetStatusImage(targetId, status, file)
    toast.success(
      cropMode.value === 'edit' ? t('desktopDecor.crop.saveOk') : t('desktopDecor.petUploadOk'),
    )
  } catch (err) {
    const code = err instanceof Error ? err.message : 'error'
    const key =
      code === 'not-image'
        ? 'desktopDecor.uploadNotImage'
        : code === 'limit'
          ? 'desktopDecor.petUploadLimit'
          : code === 'too-large'
            ? 'desktopDecor.uploadTooLarge'
            : code === 'quota'
              ? 'desktopDecor.uploadQuota'
              : 'desktopDecor.uploadFail'
    toast.error(t(key))
  } finally {
    petUploading.value = false
  }
}

async function onCropConfirm(file: File) {
  const kind = cropKind.value
  const rest = [...cropQueue.value]
  const replaceWp = cropReplaceWallpaperId.value
  const replacePet = cropReplacePetStatus.value
  cropOpen.value = false
  cropFile.value = null
  cropSrcUrl.value = null
  cropQueue.value = []
  // keep replace ids through uploadCropped, then clear
  cropReplaceWallpaperId.value = replaceWp
  cropReplacePetStatus.value = replacePet
  await uploadCropped(kind, file)
  cropReplaceWallpaperId.value = ''
  cropReplacePetStatus.value = null
  cropMode.value = 'upload'
  if (rest.length) openCrop(kind, rest)
}

async function onWallpaperFile(e: Event) {
  const input = e.target as HTMLInputElement
  const files = [...(input.files || [])]
  input.value = ''
  if (!files.length) return
  openCrop('wallpaper', files)
}

function onWallpaperPick(id: WallpaperId) {
  setWallpaper(id)
}

async function onRemoveCustomWallpaper(id: string) {
  try {
    await removeCustomWallpaper(id)
  } catch {
    toast.error(t('desktopDecor.uploadFail'))
  }
}

async function onPetFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  openCrop('pet', [file])
}

async function onCreateCustomPet() {
  try {
    const item = await createCustomPet()
    editingPetId.value = item.id
    toast.success(t('desktopDecor.petCreateOk'))
  } catch (err) {
    const code = err instanceof Error ? err.message : 'error'
    toast.error(t(code === 'limit' ? 'desktopDecor.petUploadLimit' : 'desktopDecor.uploadFail'))
  }
}

async function onRenameEditingPet(e: Event) {
  const el = e.target as HTMLInputElement
  const id = editingPet.value?.id
  if (!id) return
  try {
    await renameCustomPet(id, el.value)
  } catch {
    toast.error(t('desktopDecor.uploadFail'))
  }
}

function onEditCustomPet(id: string) {
  editingPetId.value = id
  selectCustomPet(id)
}

function onUploadStatus(status: PetTaskStatus) {
  if (!editingPet.value) return
  petUploadStatus.value = status
  petStatusFileInput.value?.click()
}

async function onClearStatus(status: PetTaskStatus) {
  const id = editingPet.value?.id
  if (!id) return
  try {
    await clearCustomPetStatusImage(id, status)
  } catch {
    toast.error(t('desktopDecor.uploadFail'))
  }
}

async function onRemoveCustomPet(id: string) {
  try {
    await removeCustomPet(id)
    if (editingPetId.value === id) {
      editingPetId.value = activeCustomPetId.value || customPets.value[0]?.id || ''
    }
  } catch {
    toast.error(t('desktopDecor.uploadFail'))
  }
}

function onPetPick(id: (typeof BUILTIN_PETS)[number]) {
  setPet(id)
}

function petPreviewUrl(petItem: (typeof customPets.value)[number]) {
  return pickCustomPetImage('idle', petItem)?.url || Object.values(petItem.images)[0]?.url || ''
}

const schema = computed(() => (store.settings?.schema?.properties || {}) as Record<string, SchemaSpec>)

const workspaceKeys = computed(() => {
  const fromApi = (store.settings as { workspace_keys?: string[] } | null)?.workspace_keys
  if (Array.isArray(fromApi) && fromApi.length) return new Set(fromApi)
  return new Set(
    Object.entries(schema.value)
      .filter(([, spec]) => spec.scope === 'workspace')
      .map(([key]) => key),
  )
})

const hasWorkspace = computed(() => Boolean(store.workspaceId))

const groups = computed(() => {
  const map = new Map<string, { id: string; title: string; icon: string; keys: string[] }>()
  const defs: Record<string, { titleKey: string; icon: string }> = {
    agent: { titleKey: 'settings.groups.agent', icon: 'atom' },
    policy: { titleKey: 'settings.groups.policy', icon: 'shield' },
    terminal: { titleKey: 'settings.groups.terminal', icon: 'terminal' },
    python: { titleKey: 'settings.groups.python', icon: 'chip' },
    llm: { titleKey: 'settings.groups.llm', icon: 'chip' },
    ui: { titleKey: 'settings.groups.ui', icon: 'sliders' },
    uploads: { titleKey: 'settings.groups.uploads', icon: 'folder' },
    storage: { titleKey: 'settings.groups.storage', icon: 'gear' },
    server: { titleKey: 'settings.groups.server', icon: 'shield' },
  }
  for (const key of Object.keys(schema.value)) {
    const isWs = workspaceKeys.value.has(key)
    if (settingsScope.value === 'workspace' ? !isWs : isWs) continue
    const prefix = key.split('.')[0] || 'other'
    const def = defs[prefix] || { titleKey: '', icon: 'gear' }
    const title = def.titleKey ? t(def.titleKey) : prefix
    const group = map.get(prefix) || { id: prefix, title, icon: def.icon, keys: [] }
    group.title = title
    group.keys.push(key)
    map.set(prefix, group)
  }
  return [...map.values()]
})

watch(groups, (list) => {
  if (settingsScope.value === 'user' && activeGroup.value === 'appearance') return
  if (list.length && !list.some((g) => g.id === activeGroup.value)) {
    activeGroup.value = settingsScope.value === 'user' ? 'appearance' : (list[0]?.id || 'appearance')
  }
}, { immediate: true })

watch(settingsScope, (scope) => {
  if (scope === 'user') {
    activeGroup.value = 'appearance'
  } else {
    activeGroup.value = groups.value[0]?.id || 'python'
    void loadPythonInterpreters()
  }
})

onMounted(async () => {
  await store.loadSettings()
  applySettingsValues(store.settings)
  if (settingsScope.value === 'workspace') void loadPythonInterpreters()
})

watch(
  () => store.settings,
  (s) => {
    if (s) applySettingsValues(s)
  },
  { immediate: true },
)

watch(
  () => store.workspaceId,
  async () => {
    await store.loadSettings()
    if (settingsScope.value === 'workspace') void loadPythonInterpreters()
  },
)

function jump(id: string) {
  activeGroup.value = id
  document.getElementById(`settings-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function specFor(key: string) {
  return schema.value[key] || {}
}

function fieldTitle(key: string) {
  const i18nKey = `settings.fields.${key}`
  return te(i18nKey) ? t(i18nKey) : (specFor(key).title || key)
}

function enumLabel(key: string, value: string) {
  const i18nKey = `settings.enums.${key}.${value}`
  return te(i18nKey) ? t(i18nKey) : value
}

function enumOptions(key: string) {
  const values = specFor(key).enum || []
  return values.map((value) => ({
    value,
    label: enumLabel(key, value),
  }))
}

function fieldPlaceholder(key: string) {
  const i18nKey = `settings.placeholders.${key}`
  if (te(i18nKey)) return t(i18nKey)
  const example = specFor(key).example
  return typeof example === 'string' ? example : ''
}

const STORAGE_URL_KEYS = new Set([
  'storage.postgres_url',
  'storage.redis_url',
  'storage.checkpoint_postgres_url',
])

const OMIT_EMPTY_KEYS = new Set([
  ...STORAGE_URL_KEYS,
  'terminal.shell',
  'uploads.dir',
  'python.interpreter',
])

const accessPasswordSet = computed(
  () => Boolean((store.settings as { access_password_set?: boolean } | null)?.access_password_set),
)

const accessPasswordOn = computed(() => Boolean(local['server.access_password_enabled']))

function applySettingsValues(payload: Record<string, unknown> | null | undefined) {
  if (!payload) return
  const userValues = (payload.user_values as Record<string, unknown> | undefined)
    || (payload.values as Record<string, unknown> | undefined)
    || {}
  const wsValues = (payload.workspace_values as Record<string, unknown> | undefined) || {}
  Object.assign(local, userValues)
  if (local['server.access_password_enabled'] == null) {
    local['server.access_password_enabled'] = false
  }
  fillEnumDefaults(local, 'user')
  baseline.value = { ...local }

  for (const key of Object.keys(localWorkspace)) {
    delete localWorkspace[key]
  }
  Object.assign(localWorkspace, wsValues)
  if (localWorkspace['python.interpreter'] == null) {
    localWorkspace['python.interpreter'] = ''
  }
  fillEnumDefaults(localWorkspace, 'workspace')
  baselineWorkspace.value = { ...localWorkspace }
}

function fillEnumDefaults(bag: Record<string, unknown>, scope: 'user' | 'workspace') {
  for (const [key, spec] of Object.entries(schema.value)) {
    const isWs = workspaceKeys.value.has(key)
    if (scope === 'workspace' ? !isWs : isWs) continue
    if (typeof bag[key] === 'string') continue
    if (!spec.enum?.length) continue
    bag[key] = typeof spec.default === 'string' ? spec.default : spec.enum[0]
  }
}

function settingsBag() {
  return settingsScope.value === 'workspace' ? localWorkspace : local
}

function stringSetting(key: string) {
  const raw = settingsBag()[key]
  return typeof raw === 'string' ? raw : ''
}

function setStringSetting(key: string, value: string) {
  settingsBag()[key] = value
}

function buildSettingsPatch(scope: 'user' | 'workspace') {
  const patch: Record<string, unknown> = {}
  const source = scope === 'workspace' ? localWorkspace : local
  const base = scope === 'workspace' ? baselineWorkspace.value : baseline.value
  for (const [key, value] of Object.entries(source)) {
    if (scope === 'user' && workspaceKeys.value.has(key)) continue
    if (scope === 'workspace' && !workspaceKeys.value.has(key)) continue
    // Access password: empty means "unchanged" (never leak/clear accidentally).
    if (key === 'server.access_password' && (value === '' || value == null)) {
      continue
    }
    if (OMIT_EMPTY_KEYS.has(key) && (value === '' || value == null)) {
      const prev = base[key]
      // Clearing a previously set optional field must PATCH "" so the server drops it.
      if (prev !== '' && prev != null) patch[key] = ''
      continue
    }
    patch[key] = value
  }
  return patch
}

async function clearAccessPassword() {
  if (saving.value) return
  saving.value = true
  try {
    await store.saveSettings({
      'server.access_password': '',
      'server.access_password_enabled': false,
    }, 'user')
    local['server.access_password'] = ''
    local['server.access_password_enabled'] = false
    baseline.value = {
      ...baseline.value,
      'server.access_password': '',
      'server.access_password_enabled': false,
    }
    applySettingsValues(store.settings as Record<string, unknown> | null)
    toast.success(t('accessGate.cleared'))
  } catch (err) {
    toast.error(err instanceof Error ? err.message : String(err))
  } finally {
    saving.value = false
  }
}

const storageStatus = computed(() => (store.settings as { storage?: Record<string, unknown> } | null)?.storage || null)
const uploadsResolved = computed(
  () => (store.settings as { uploads_resolved?: string } | null)?.uploads_resolved || '',
)
const isDesktop = Boolean(
  (window as Window & { codeAgentDesktop?: { isDesktop?: boolean; pickDirectory?: () => Promise<string | null> } })
    .codeAgentDesktop?.isDesktop,
)

function fieldModel(_key?: string) {
  return settingsScope.value === 'workspace' ? localWorkspace : local
}

function pythonInterpreterOptionLabel(item: PythonInterpreterItem) {
  if (item.kind === 'system') {
    return item.version
      ? t('settings.python.systemWithVersion', { path: item.path, version: item.version })
      : t('settings.python.systemPath', { path: item.path })
  }
  return item.label || item.path
}

const pythonInterpreterSelectOptions = computed(() => {
  const opts: { value: string; label: string }[] = [
    { value: '', label: t('settings.python.autoDetect') },
    ...pythonInterpreters.value.map((item) => ({
      value: item.path,
      label: pythonInterpreterOptionLabel(item),
    })),
  ]
  const current = String(localWorkspace['python.interpreter'] ?? '')
  if (current && !opts.some((o) => o.value === current)) {
    opts.push({ value: current, label: t('settings.python.customPath', { path: current }) })
  }
  return opts
})

const canPickPythonFolder = computed(
  () => isDesktop && store.workspace?.kind !== 'ssh' && Boolean(store.workspace?.root_path),
)

function pathRelativeToWorkspace(absPath: string, wsRoot: string): string {
  const normalized = absPath.replace(/\\/g, '/').replace(/\/+$/, '')
  const root = wsRoot.replace(/\\/g, '/').replace(/\/+$/, '')
  if (normalized === root) return '.'
  const prefix = `${root}/`
  if (normalized.startsWith(prefix)) return normalized.slice(prefix.length)
  return absPath
}

async function loadPythonInterpreters() {
  if (!store.workspaceId) {
    pythonInterpreters.value = []
    return
  }
  pythonInterpretersLoading.value = true
  try {
    const res = await api<{ items?: PythonInterpreterItem[] }>(
      `/api/workspaces/${store.workspaceId}/python/interpreters`,
    )
    pythonInterpreters.value = Array.isArray(res?.items) ? res.items : []
  } catch {
    pythonInterpreters.value = []
  } finally {
    pythonInterpretersLoading.value = false
  }
}

async function pickPythonInterpreter() {
  const desktop = getDesktopBridge()
  const wsRoot = store.workspace?.root_path
  if (!desktop?.pickDirectory || !wsRoot) return
  try {
    const chosen = await desktop.pickDirectory()
    if (!chosen) return
    localWorkspace['python.interpreter'] = pathRelativeToWorkspace(chosen, wsRoot)
  } catch {
    /* ignore cancel / picker errors */
  }
}

async function pickDirectory(key: string) {
  const desktop = (
    window as Window & { codeAgentDesktop?: { pickDirectory?: () => Promise<string | null> } }
  ).codeAgentDesktop
  if (!desktop?.pickDirectory) return
  try {
    const chosen = await desktop.pickDirectory()
    if (!chosen) return
    fieldModel(key)[key] = chosen
  } catch {
    /* ignore cancel / picker errors */
  }
}

async function save() {
  if (saving.value) return
  if (settingsScope.value === 'workspace' && !hasWorkspace.value) {
    toast.error(t('settings.workspaceRequired'))
    return
  }
  if (settingsScope.value === 'user') {
    const enabling = Boolean(local['server.access_password_enabled'])
    const typed = String(local['server.access_password'] || '').trim()
    if (enabling && !accessPasswordSet.value && !typed) {
      toast.error(t('accessGate.needPassword'))
      return
    }
  }
  saving.value = true
  try {
    await store.saveSettings(buildSettingsPatch(settingsScope.value), settingsScope.value)
    applySettingsValues(store.settings as Record<string, unknown> | null)
    saved.value = true
    toast.success(t('common.saved'))
    setTimeout(() => { saved.value = false }, 2000)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : t('common.saveFailed'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="panel-shell settings-panel">
    <div class="panel-body">
      <header class="page-head">
        <div>
          <h1 class="page-title">{{ t('settings.title') }}</h1>
          <p class="page-lead">
            {{ settingsScope === 'workspace' ? t('settings.leadWorkspace') : t('settings.leadUser') }}
          </p>
          <div class="settings-scope" role="tablist" :aria-label="t('settings.scopeLabel')">
            <button
              type="button"
              role="tab"
              :aria-selected="settingsScope === 'user'"
              :class="{ active: settingsScope === 'user' }"
              @click="settingsScope = 'user'"
            >
              {{ t('settings.scopeUser') }}
            </button>
            <button
              type="button"
              role="tab"
              :aria-selected="settingsScope === 'workspace'"
              :class="{ active: settingsScope === 'workspace' }"
              :disabled="!hasWorkspace"
              :title="hasWorkspace ? undefined : t('settings.workspaceRequired')"
              @click="settingsScope = 'workspace'"
            >
              {{ t('settings.scopeWorkspace') }}
            </button>
          </div>
        </div>
        <button
          type="button"
          class="btn btn-primary btn-save"
          :class="{ saved }"
          :disabled="saving || (settingsScope === 'workspace' && !hasWorkspace)"
          @click="save"
        >
          <AppIcon :name="saved ? 'check' : 'save'" :size="13" :stroke-width="1.75" />
          {{ saved ? t('common.saved') : t('settings.save') }}
        </button>
      </header>

      <div class="settings-layout">
        <nav class="settings-toc" :aria-label="t('settings.toc')">
          <button
            v-if="settingsScope === 'user'"
            type="button"
            :class="{ active: activeGroup === 'appearance' }"
            @click="jump('appearance')"
          >
            <AppIcon name="sliders" :size="16" :stroke-width="1.75" />
            {{ t('settings.groups.appearance') }}
          </button>
          <button
            v-for="group in groups"
            :key="group.id"
            type="button"
            :class="{ active: activeGroup === group.id }"
            @click="jump(group.id)"
          >
            <AppIcon :name="group.icon" :size="16" :stroke-width="1.75" />
            {{ group.title }}
          </button>
        </nav>
        <div class="settings-main">
          <p v-if="settingsScope === 'workspace' && !hasWorkspace" class="workspace-needed">
            {{ t('settings.workspaceRequired') }}
          </p>
          <section v-if="settingsScope === 'user'" id="settings-appearance" class="settings-group">
            <div class="group-head">
              <span class="group-icon"><AppIcon name="sliders" :size="18" /></span>
              <h2>{{ t('settings.groups.appearance') }}</h2>
            </div>
            <div class="setting-row">
              <div class="setting-copy">
                <label>{{ t('language.label') }}</label>
                <p class="setting-key">{{ t('settings.languageLead') }}</p>
              </div>
              <LanguageSelect :show-label="false" />
            </div>
            <div class="setting-row">
              <div class="setting-copy">
                <label for="editor-theme">{{ t('settings.editorTheme') }}</label>
                <p class="setting-key">{{ t('settings.editorThemeLead') }}</p>
              </div>
              <FormSelect
                id="editor-theme"
                class="setting-select"
                :model-value="editorThemeId"
                :options="editorThemeOptions"
                @update:model-value="onEditorThemeChange"
              />
            </div>
            <div class="setting-row">
              <div class="setting-copy">
                <label for="ports-notify-new">{{ t('settings.portsNotify') }}</label>
                <p class="setting-key">{{ t('settings.portsNotifyLead') }}</p>
              </div>
              <label class="toggle">
                <input
                  id="ports-notify-new"
                  type="checkbox"
                  :checked="portsNotifyNew"
                  @change="onPortsNotifyToggle(($event.target as HTMLInputElement).checked)"
                />
                <span class="toggle-track" />
              </label>
            </div>
            <div class="setting-row">
              <div class="setting-copy">
                <label>{{ t('settings.logo') }}</label>
                <p class="setting-key">{{ t('settings.logoLead') }}</p>
              </div>
              <div class="logo-pick" role="radiogroup" :aria-label="t('settings.logo')">
                <button
                  v-for="id in BRAND_MARKS"
                  :key="id"
                  type="button"
                  class="logo-pick-btn"
                  role="radio"
                  :aria-checked="brandMark === id"
                  :class="{ active: brandMark === id }"
                  :title="t(`settings.logos.${id}`)"
                  @click="setBrandMark(id)"
                >
                  <BrandMark :variant="id" :size="36" />
                  <span>{{ t(`settings.logos.${id}`) }}</span>
                </button>
              </div>
            </div>
            <div class="setting-row">
              <div class="setting-copy">
                <label>{{ t('desktopDecor.wallpaper') }}</label>
                <p class="setting-key">{{ t('desktopDecor.wallpaperLead') }}</p>
              </div>
              <div class="decor-wallpaper-wrap">
                <div class="decor-pick" role="radiogroup" :aria-label="t('desktopDecor.wallpaper')">
                  <button
                    v-for="id in BUILTIN_WALLPAPERS"
                    :key="id"
                    type="button"
                    class="decor-pick-btn"
                    role="radio"
                    :aria-checked="wallpaper === id"
                    :class="[{ active: wallpaper === id }, `wp-swatch-${id}`]"
                    :title="t(`desktopDecor.wallpapers.${id}`)"
                    @click="onWallpaperPick(id)"
                  >
                    <span class="decor-swatch" />
                    <span>{{ t(`desktopDecor.wallpapers.${id}`) }}</span>
                  </button>
                </div>
                <div class="decor-gallery-head">
                  <span class="setting-key">{{ t('desktopDecor.customGallery') }}</span>
                  <button
                    type="button"
                    class="choice-btn"
                    :disabled="wallpaperUploading"
                    @click="wallpaperFileInput?.click()"
                  >
                    <AppIcon name="folder" :size="14" :stroke-width="1.75" />
                    {{ t('desktopDecor.uploadImage') }}
                  </button>
                </div>
                <p class="setting-key decor-size-hint">{{ t('desktopDecor.wallpaperSizeHint') }}</p>
                <div v-if="customWallpapers.length" class="decor-gallery" role="list">
                  <div
                    v-for="item in customWallpapers"
                    :key="item.id"
                    class="decor-gallery-item"
                    :class="{ active: wallpaper === 'custom' && activeCustomId === item.id }"
                    role="listitem"
                  >
                    <button
                      type="button"
                      class="decor-gallery-thumb"
                      :title="t('desktopDecor.useImage')"
                      :style="{ backgroundImage: `url(${item.url})` }"
                      @click="selectCustomWallpaper(item.id)"
                    />
                    <button
                      v-if="canRecropMime(item.mime)"
                      type="button"
                      class="decor-gallery-crop"
                      :title="t('desktopDecor.cropAgain')"
                      :aria-label="t('desktopDecor.cropAgain')"
                      :disabled="wallpaperUploading"
                      @click="openRecropWallpaper(item.id, item.url, item.mime)"
                    >
                      {{ t('desktopDecor.cropAgain') }}
                    </button>
                    <button
                      type="button"
                      class="decor-gallery-del"
                      :title="t('desktopDecor.deleteImage')"
                      :aria-label="t('desktopDecor.deleteImage')"
                      @click="onRemoveCustomWallpaper(item.id)"
                    >
                      ×
                    </button>
                  </div>
                </div>
                <p v-else class="setting-key decor-gallery-empty">{{ t('desktopDecor.customEmpty') }}</p>
                <input
                  ref="wallpaperFileInput"
                  type="file"
                  accept="image/*"
                  multiple
                  class="sr-only"
                  @change="onWallpaperFile"
                />
              </div>
            </div>
            <div class="setting-row">
              <div class="setting-copy">
                <label>{{ t('desktopDecor.pet') }}</label>
                <p class="setting-key">{{ t('desktopDecor.petLead') }}</p>
              </div>
              <div class="decor-wallpaper-wrap">
                <div class="decor-pick" role="radiogroup" :aria-label="t('desktopDecor.pet')">
                  <button
                    v-for="id in BUILTIN_PETS"
                    :key="id"
                    type="button"
                    class="decor-pick-btn"
                    role="radio"
                    :aria-checked="pet === id"
                    :class="{ active: pet === id }"
                    :title="t(`desktopDecor.pets.${id}`)"
                    @click="onPetPick(id)"
                  >
                    <span class="pet-swatch" :class="`pet-swatch-${id}`">{{ id === 'none' ? '—' : '' }}</span>
                    <span>{{ t(`desktopDecor.pets.${id}`) }}</span>
                  </button>
                </div>

                <div class="decor-gallery-head">
                  <span class="setting-key">{{ t('desktopDecor.petGallery') }}</span>
                  <button type="button" class="choice-btn" @click="onCreateCustomPet">
                    <AppIcon name="plus" :size="14" :stroke-width="1.75" />
                    {{ t('desktopDecor.petCreate') }}
                  </button>
                </div>
                <p class="setting-key decor-size-hint">{{ t('desktopDecor.petSizeHint') }}</p>
                <p class="setting-key decor-gallery-empty">{{ t('desktopDecor.petGalleryLead') }}</p>

                <div v-if="customPets.length" class="pet-profile-list" role="list">
                  <button
                    v-for="item in customPets"
                    :key="item.id"
                    type="button"
                    class="pet-profile-chip"
                    role="listitem"
                    :class="{ active: pet === 'custom' && activeCustomPetId === item.id }"
                    @click="onEditCustomPet(item.id)"
                  >
                    <span
                      class="pet-swatch pet-swatch-custom"
                      :style="
                        petPreviewUrl(item)
                          ? { backgroundImage: `url(${petPreviewUrl(item)})` }
                          : undefined
                      "
                    />
                    <span class="pet-profile-name">{{ item.name }}</span>
                    <span
                      class="decor-gallery-del pet-profile-del"
                      role="button"
                      tabindex="0"
                      :title="t('desktopDecor.petDelete')"
                      @click.stop="onRemoveCustomPet(item.id)"
                      @keydown.enter.stop="onRemoveCustomPet(item.id)"
                    >×</span>
                  </button>
                </div>

                <div v-if="editingPet" class="pet-editor">
                  <div class="pet-editor-head">
                    <label class="setting-key" for="pet-name-input">{{ t('desktopDecor.petName') }}</label>
                    <input
                      id="pet-name-input"
                      class="pet-name-input"
                      type="text"
                      :value="editingPet.name"
                      @change="onRenameEditingPet"
                    />
                  </div>
                  <p class="setting-key">{{ t('desktopDecor.petStatusesLead') }}</p>
                  <div class="pet-status-grid">
                    <div
                      v-for="status in PET_TASK_STATUSES"
                      :key="status"
                      class="pet-status-card"
                    >
                      <div
                        class="pet-status-thumb"
                        :class="{ empty: !editingPet.images[status] }"
                        :style="
                          editingPet.images[status]
                            ? { backgroundImage: `url(${editingPet.images[status]!.url})` }
                            : undefined
                        "
                      />
                      <div class="pet-status-meta">
                        <strong>{{ t(`desktopDecor.petStatuses.${status}`) }}</strong>
                        <div class="pet-status-actions">
                          <button
                            type="button"
                            class="choice-btn"
                            :disabled="petUploading"
                            @click="onUploadStatus(status)"
                          >
                            {{ editingPet.images[status] ? t('desktopDecor.replaceImage') : t('desktopDecor.petUpload') }}
                          </button>
                          <button
                            v-if="editingPet.images[status] && canRecropMime(editingPet.images[status]?.mime)"
                            type="button"
                            class="choice-btn"
                            :disabled="petUploading"
                            @click="openRecropPetStatus(status)"
                          >
                            {{ t('desktopDecor.cropAgain') }}
                          </button>
                          <button
                            v-if="editingPet.images[status]"
                            type="button"
                            class="choice-btn"
                            @click="onClearStatus(status)"
                          >
                            {{ t('desktopDecor.clearImage') }}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <input
                  ref="petStatusFileInput"
                  type="file"
                  accept="image/*,.gif,.webp,.png,.jpg,.jpeg,.apng"
                  class="sr-only"
                  @change="onPetFile"
                />
              </div>
            </div>
            <div class="setting-row">
              <div class="setting-copy">
                <label>{{ t('git.diffTarget') }}</label>
                <p class="setting-key">{{ t('git.diffTargetLead') }}</p>
              </div>
              <div class="choice-row" role="radiogroup" :aria-label="t('git.diffTarget')">
                <button
                  type="button"
                  class="choice-btn"
                  role="radio"
                  :aria-checked="diffTarget === 'panel'"
                  :class="{ active: diffTarget === 'panel' }"
                  @click="setDiffTarget('panel')"
                >
                  <AppIcon name="git" :size="14" :stroke-width="1.75" />
                  {{ t('git.diffTargetPanel') }}
                </button>
                <button
                  type="button"
                  class="choice-btn"
                  role="radio"
                  :aria-checked="diffTarget === 'editor'"
                  :class="{ active: diffTarget === 'editor' }"
                  @click="setDiffTarget('editor')"
                >
                  <AppIcon name="file" :size="14" :stroke-width="1.75" />
                  {{ t('git.diffTargetEditor') }}
                </button>
              </div>
            </div>
            <LayoutControls />
          </section>
          <section v-for="group in groups" :id="`settings-${group.id}`" :key="group.id" class="settings-group">
            <div class="group-head">
              <span class="group-icon"><AppIcon :name="group.icon" :size="18" /></span>
              <h2>{{ group.title }}</h2>
            </div>

          <div
            v-for="key in group.keys"
            v-show="key !== 'server.access_password' || accessPasswordOn"
            :key="key"
            class="setting-row"
            :class="{ required: key === 'server.access_password' && accessPasswordOn }"
          >
            <div class="setting-copy">
              <label :for="key">
                {{ fieldTitle(key) }}
                <span v-if="key === 'server.access_password' && accessPasswordOn" class="req-mark">{{ t('accessGate.required') }}</span>
              </label>
              <code v-if="key.includes('.')" class="setting-key">{{ key }}</code>
            </div>

            <FormSelect
              v-if="specFor(key).enum"
              :id="key"
              class="setting-select"
              :model-value="stringSetting(key)"
              :options="enumOptions(key)"
              @update:model-value="setStringSetting(key, $event)"
            />

            <textarea
              v-else-if="specFor(key).format === 'textarea'"
              :id="key"
              v-model="(settingsScope === 'workspace' ? localWorkspace : local)[key] as string"
              class="field-control setting-input"
              rows="4"
            />

            <label v-else-if="specFor(key).type === 'boolean'" class="toggle">
              <input :id="key" v-model="(settingsScope === 'workspace' ? localWorkspace : local)[key]" type="checkbox" />
              <span class="toggle-track" />
            </label>

            <input
              v-else-if="specFor(key).type === 'integer' || specFor(key).type === 'number'"
              :id="key"
              v-model.number="(settingsScope === 'workspace' ? localWorkspace : local)[key]"
              class="field-control setting-input"
              type="number"
              :min="specFor(key).minimum"
              :max="specFor(key).maximum"
              step="any"
            />

            <template v-else-if="specFor(key).format === 'password'">
              <div class="password-field">
                <input
                  :id="key"
                  v-model="(settingsScope === 'workspace' ? localWorkspace : local)[key]"
                  class="field-control setting-input"
                  type="password"
                  autocomplete="off"
                  :required="key === 'server.access_password' && accessPasswordOn && !accessPasswordSet"
                  :placeholder="
                    key === 'server.access_password' && accessPasswordSet
                      ? t('accessGate.placeholderKeep')
                      : key === 'server.access_password'
                        ? t('accessGate.placeholderRequired')
                        : fieldPlaceholder(key)
                  "
                />
                <div v-if="key === 'server.access_password'" class="access-password-bar">
                  <span v-if="accessPasswordSet" class="access-status on">{{ t('accessGate.passwordSet') }}</span>
                  <button
                    v-if="accessPasswordSet"
                    type="button"
                    class="btn btn-ghost access-clear-btn"
                    :disabled="saving"
                    @click="clearAccessPassword"
                  >
                    {{ t('accessGate.clear') }}
                  </button>
                </div>
                <p v-if="key === 'server.access_password'" class="access-password-hint">
                  <template v-if="accessPasswordSet">{{ t('accessGate.hintWhenOnSet') }}</template>
                  <template v-else>{{ t('accessGate.hintWhenOnUnset') }}</template>
                </p>
              </div>
            </template>

            <div v-else-if="key === 'python.interpreter'" class="python-interpreter-field">
              <FormSelect
                :id="key"
                class="setting-select python-interpreter-select"
                :disabled="pythonInterpretersLoading"
                :model-value="stringSetting(key)"
                :options="pythonInterpreterSelectOptions"
                :placeholder="t('settings.python.autoDetect')"
                @update:model-value="setStringSetting(key, $event)"
              />
              <div class="setting-path python-interpreter-path">
                <input
                  :id="`${key}-path`"
                  v-model="localWorkspace['python.interpreter'] as string"
                  class="field-control setting-input"
                  type="text"
                  :placeholder="fieldPlaceholder(key)"
                />
                <button
                  v-if="canPickPythonFolder"
                  type="button"
                  class="btn setting-browse"
                  @click="pickPythonInterpreter"
                >
                  <AppIcon name="folder" :size="14" :stroke-width="1.75" />
                  {{ t('settings.python.browse') }}
                </button>
              </div>
              <p v-if="pythonInterpretersLoading" class="setting-hint">{{ t('settings.python.scanning') }}</p>
              <p v-else-if="!pythonInterpreters.length" class="setting-hint">{{ t('settings.python.noneFound') }}</p>
            </div>

            <div v-else-if="specFor(key).format === 'directory'" class="setting-path">
              <input
                :id="key"
                v-model="(settingsScope === 'workspace' ? localWorkspace : local)[key] as string"
                class="field-control setting-input"
                type="text"
                :placeholder="fieldPlaceholder(key)"
              />
              <button
                v-if="isDesktop"
                type="button"
                class="btn setting-browse"
                @click="pickDirectory(key)"
              >
                <AppIcon name="folder" :size="14" :stroke-width="1.75" />
                {{ t('workspace.pickFolder') }}
              </button>
            </div>

            <input
              v-else
              :id="key"
              v-model="(settingsScope === 'workspace' ? localWorkspace : local)[key]"
              class="field-control setting-input"
              :placeholder="fieldPlaceholder(key)"
            />
          </div>
          <p v-if="group.id === 'uploads'" class="storage-note">
            {{ t('settings.uploads.hint') }}
            <template v-if="uploadsResolved">
              <br />
              <span class="uploads-resolved">{{ t('settings.uploads.resolved', { path: uploadsResolved }) }}</span>
            </template>
          </p>
          <p v-if="group.id === 'storage'" class="storage-note">{{ t('settings.storage.restartHint') }}</p>
          <dl v-if="group.id === 'storage' && storageStatus" class="storage-status">
            <div><dt>{{ t('settings.storage.activeDatabase') }}</dt><dd>{{ storageStatus.database }}</dd></div>
            <div><dt>{{ t('settings.storage.activeEvents') }}</dt><dd>{{ storageStatus.events }}</dd></div>
            <div><dt>{{ t('settings.storage.activeCheckpoint') }}</dt><dd>{{ storageStatus.checkpoint }}</dd></div>
          </dl>
        </section>
        </div>
      </div>
    </div>
    <ImageCropDialog
      :open="cropOpen"
      :file="cropFile"
      :src-url="cropSrcUrl"
      :kind="cropKind"
      :mode="cropMode"
      @close="closeCrop"
      @confirm="onCropConfirm"
    />
  </div>
</template>

<style scoped>
.settings-panel .panel-body {
  padding: 16px 20px 24px;
  overflow: auto;
  font-size: 12px;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.page-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-h);
}
.page-lead {
  margin: 0;
  max-width: 520px;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
}
.settings-scope {
  display: inline-flex;
  gap: 2px;
  margin-top: 10px;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--code-bg);
}
.settings-scope button {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  padding: 5px 10px;
  border-radius: 6px;
  cursor: pointer;
}
.settings-scope button:hover:not(:disabled) {
  color: var(--text-h);
}
.settings-scope button.active {
  background: var(--panel-bg);
  color: var(--primary);
  font-weight: 600;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--border) 80%, transparent);
}
.settings-scope button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.workspace-needed {
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: 12px;
}
.page-head .btn-save {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 560;
  border-radius: 6px;
}
.page-head .btn-save.saved {
  background: color-mix(in srgb, var(--primary) 80%, #059669);
}
.settings-layout {
  display: grid;
  grid-template-columns: 148px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.settings-toc {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.settings-toc button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.settings-toc button:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.settings-toc button.active {
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 600;
}
@media (max-width: 720px) {
  .settings-layout {
    grid-template-columns: 1fr;
  }
  .settings-toc {
    position: static;
    flex-direction: row;
    flex-wrap: wrap;
  }
  .settings-toc button {
    width: auto;
  }
}
.settings-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.settings-group {
  scroll-margin-top: 8px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  padding: 12px 14px;
}
.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: var(--border-width) solid var(--border);
}
.group-icon {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--primary-soft);
  color: var(--primary);
  flex-shrink: 0;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 16%, transparent);
}
.group-head h2 {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}
.setting-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 0;
  border-bottom: var(--border-width) solid var(--border);
}
.setting-row:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}
.choice-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.choice-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  color: var(--text-h);
  font-size: 12px;
  cursor: pointer;
}
.choice-btn:hover {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 6%, var(--panel-bg));
}
.choice-btn.active {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 10%, var(--panel-bg));
  color: var(--primary);
  font-weight: 600;
}
.logo-pick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.decor-pick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.decor-pick-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  width: 84px;
  padding: 8px 6px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  color: var(--text-h);
  font-size: 11px;
  cursor: pointer;
}
.decor-pick-btn:hover {
  border-color: var(--primary);
}
.decor-pick-btn.active {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 10%, var(--panel-bg));
  color: var(--primary);
  font-weight: 600;
}
.decor-swatch {
  width: 56px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--code-bg);
}
.wp-swatch-none .decor-swatch {
  background:
    linear-gradient(135deg, transparent 46%, var(--border-strong) 46% 54%, transparent 54%),
    var(--code-bg);
}
.wp-swatch-aurora .decor-swatch {
  background: linear-gradient(135deg, #0b1a1f, #1a4a6e 45%, #38bd94);
}
.wp-swatch-dusk .decor-swatch {
  background: linear-gradient(135deg, #1a1210, #6b2d1f 50%, #e87848);
}
.wp-swatch-harbor .decor-swatch {
  background: linear-gradient(180deg, #e8eef5, #6f8fad);
}
.wp-swatch-custom .decor-swatch {
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--primary) 35%, var(--code-bg)), var(--code-bg));
}
.decor-wallpaper-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
  width: 100%;
  max-width: 520px;
}
.decor-gallery-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
}
.decor-gallery {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  width: 100%;
}
.decor-gallery-item {
  position: relative;
  width: 88px;
  height: 56px;
}
.decor-gallery-thumb {
  width: 100%;
  height: 100%;
  border: var(--border-width) solid var(--border);
  border-radius: 8px;
  background-color: var(--code-bg);
  background-size: cover;
  background-position: center;
  cursor: pointer;
  padding: 0;
}
.decor-gallery-item.active .decor-gallery-thumb {
  border-color: var(--primary);
  box-shadow: 0 0 0 1px var(--primary);
}
.decor-gallery-crop {
  position: absolute;
  left: 4px;
  bottom: 4px;
  z-index: 1;
  border: 0;
  border-radius: 4px;
  padding: 2px 5px;
  font-size: 10px;
  line-height: 1.2;
  background: color-mix(in srgb, var(--panel-bg) 92%, transparent);
  color: var(--text-h);
  box-shadow: 0 0 0 1px var(--border);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s ease;
}
.decor-gallery-item:hover .decor-gallery-crop,
.decor-gallery-item:focus-within .decor-gallery-crop {
  opacity: 1;
}
.decor-gallery-crop:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.decor-gallery-del {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 999px;
  background: var(--panel-bg);
  color: var(--text-muted);
  box-shadow: 0 0 0 1px var(--border-strong);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  display: grid;
  place-items: center;
  padding: 0;
}
.decor-gallery-del:hover {
  color: #fff;
  background: #e81123;
  box-shadow: none;
}
.decor-gallery-empty {
  margin: 0;
}
.decor-size-hint {
  margin: 0;
  color: var(--text-muted);
}
.decor-wallpaper-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.pet-swatch {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: var(--code-bg);
  border: 1px solid var(--border);
  font-size: 16px;
  color: var(--text-muted);
  background-size: cover;
  background-position: center;
}
.pet-swatch-fox {
  background: radial-gradient(circle at 40% 40%, #f0a06a, #e07a3a);
}
.pet-swatch-owl {
  background: radial-gradient(circle at 40% 40%, #f5e6c8, #6b5b4a);
}
.pet-swatch-bot {
  background: radial-gradient(circle at 40% 40%, #dbe4ff, #4f6bff);
}
.pet-swatch-custom {
  background-color: var(--code-bg);
}
.pet-profile-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}
.pet-profile-chip {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  width: 88px;
  padding: 8px 6px 10px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  color: var(--text-h);
  font-size: 11px;
  cursor: pointer;
}
.pet-profile-chip.active {
  border-color: var(--primary);
  color: var(--primary);
  font-weight: 600;
}
.pet-profile-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pet-profile-del {
  position: absolute;
  top: -6px;
  right: -6px;
}
.pet-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--code-bg) 55%, var(--panel-bg));
}
.pet-editor-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.pet-name-input {
  flex: 1;
  min-width: 140px;
  height: 30px;
  padding: 0 10px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text-h);
  font-size: 13px;
}
.pet-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}
.pet-status-card {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 8px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
}
.pet-status-thumb {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background-color: var(--code-bg);
  background-size: contain;
  background-repeat: no-repeat;
  background-position: center;
  flex-shrink: 0;
}
.pet-status-thumb.empty {
  background-image:
    linear-gradient(135deg, transparent 46%, var(--border-strong) 46% 54%, transparent 54%);
}
.pet-status-meta {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pet-status-meta strong {
  font-size: 12px;
  color: var(--text-h);
}
.pet-status-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pet-upload-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.pet-status-select {
  min-width: 120px;
  width: 140px;
}
.pet-gallery {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.pet-gallery-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 28px 8px 8px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
}
.pet-gallery-thumb {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background-color: var(--code-bg);
  background-size: contain;
  background-repeat: no-repeat;
  background-position: center;
  flex-shrink: 0;
}
.pet-gallery-del {
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
}
.logo-pick-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  width: 76px;
  padding: 8px 6px 7px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  color: var(--text);
  font-size: 11px;
  cursor: pointer;
}
.logo-pick-btn:hover {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 6%, var(--panel-bg));
}
.logo-pick-btn.active {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 10%, var(--panel-bg));
  color: var(--primary);
  font-weight: 600;
}
.setting-copy label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}
.setting-key {
  display: block;
  margin-top: 1px;
  font-size: 10px;
  font-family: var(--mono);
  color: var(--text-muted);
}
.setting-input {
  width: 100%;
  font-size: 12px;
  padding: 6px 9px;
}
.setting-path {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
}
.setting-path .setting-input {
  flex: 1;
  min-width: 0;
}
.setting-browse {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  height: 30px;
  padding: 0 10px;
  font-size: 12px;
}
.uploads-resolved {
  font-family: var(--mono);
  font-size: 10px;
  word-break: break-all;
}
.setting-select {
  max-width: 360px;
}
.python-interpreter-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  min-width: 0;
}
.python-interpreter-select {
  max-width: none;
}
.python-interpreter-path {
  width: 100%;
}
.setting-hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.45;
}
.setting-input.field-control {
  min-height: 30px;
}
.toggle {
  position: relative;
  width: 40px;
  height: 22px;
  cursor: pointer;
}
.toggle input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.toggle-track {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: var(--code-bg);
  border: var(--border-width) solid var(--border);
  transition: background 0.15s ease, border-color 0.15s ease;
}
.toggle-track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--panel-bg);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  transition: transform 0.15s ease;
}
.toggle input:checked + .toggle-track {
  background: var(--primary-soft);
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
}
.toggle input:checked + .toggle-track::after {
  transform: translateX(18px);
  background: var(--primary);
}
.storage-note {
  margin: 8px 0 0;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--primary) 8%, var(--panel-bg));
  border: var(--border-width) solid color-mix(in srgb, var(--primary) 20%, var(--border));
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.45;
}
.linkish {
  margin-left: 8px;
  border: 0;
  background: transparent;
  color: var(--primary, #f59e0b);
  cursor: pointer;
  font-size: 11px;
  padding: 0;
  text-decoration: underline;
}
.password-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  min-width: 0;
}
.access-password-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.access-status {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  padding: 2px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--text-muted) 12%, transparent);
}
.access-status.on {
  color: #059669;
  background: color-mix(in srgb, #10b981 16%, transparent);
}
.access-clear-btn {
  font-size: 12px;
  padding: 4px 10px;
}
.access-password-hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.45;
}
.req-mark {
  margin-left: 6px;
  font-size: 11px;
  font-weight: 600;
  color: #dc2626;
}
.setting-row.required .setting-input {
  border-color: color-mix(in srgb, #dc2626 35%, var(--border));
}
.storage-status {
  display: grid;
  gap: 6px;
  margin: 10px 0 0;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--code-bg);
  font-size: 11px;
}
.storage-status div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.storage-status dt {
  margin: 0;
  color: var(--text-muted);
}
.storage-status dd {
  margin: 0;
  font-family: var(--mono);
  color: var(--text-h);
}</style>
