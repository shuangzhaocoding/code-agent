<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore, type Conversation, type Workspace } from '@/stores/app'
import { api } from '@/api/http'
import AppIcon from '@/components/AppIcon.vue'
import WorkspaceSwitch from '@/components/WorkspaceSwitch.vue'
import type { WorkspaceSwitchPrefill } from '@/components/WorkspaceSwitch.vue'
import WorkspaceEditDialog from '@/components/WorkspaceEditDialog.vue'
import WorkspaceFolderNode from '@/components/WorkspaceFolderNode.vue'
import WorkspaceHostBlock from '@/components/WorkspaceHostBlock.vue'
import ContextMenu, { type ContextMenuItem } from '@/components/ContextMenu.vue'
import { useSessionPins } from '@/composables/useSessionPins'
import { useToast } from '@/composables/useToast'
import { formatRelativeTime, formatWorkspaceOpenedAt } from '@/utils/relativeTime'
import {
  buildFolderForest,
  childFolderPath,
  collectAllFolderPaths,
  copyExtraHostSubtree,
  folderLeafName,
  forgetHostGroup,
  isSameOrDescendant,
  isUnderFolder,
  loadExtraHostGroups,
  normalizeFolderPath,
  parentFolderPath,
  rememberHostGroup,
  rewriteExtraHostGroups,
  rewriteFolderPrefix,
  sanitizeFolderName,
  uniqueSiblingPath,
} from '@/utils/sshHostGroups'
import {
  formatSshEndpoint,
  getSshHostClipboard,
  hasSshHostClipboard,
  setSshHostClipboard,
  subscribeSshHostClipboard,
  uniqueHostCopyName,
} from '@/utils/sshHostClipboard'

const PREVIEW_LIMIT = 5

type WorkspaceHostGroup = {
  key: string
  label: string
  kind: 'local' | 'ssh'
  groupName: string
  workspaces: Workspace[]
}

const { t } = useI18n()
const toast = useToast()
const store = useAppStore()
const pins = useSessionPins()
const showOpen = ref(false)
const openPrefill = ref<WorkspaceSwitchPrefill | null>(null)
const editingHost = ref<WorkspaceHostGroup | null>(null)
const expandedIds = ref<Set<string>>(new Set())
const showAllIds = ref<Set<string>>(new Set())
const convMap = reactive<Record<string, Conversation[]>>({})
const loading = reactive<Record<string, boolean>>({})
const errors = reactive<Record<string, string>>({})
const openingId = ref<string | null>(null)
const switchingId = ref<string | null>(null)
const creatingId = ref<string | null>(null)
const removingId = ref<string | null>(null)
const editingId = ref<string | null>(null)
const editingTitle = ref('')
const pinTick = ref(0)
const extraGroups = ref<string[]>(loadExtraHostGroups())

const hoverId = ref<string | null>(null)
const hoverHostKey = ref<string | null>(null)
const hoverReady = ref(false)
const tipStyle = ref<Record<string, string>>({})
const tipEl = ref<HTMLElement | null>(null)
let hoverHideTimer = 0
let tipRaf = 0

onMounted(async () => {
  await store.loadWorkspaces()
  unsubClipboard = subscribeSshHostClipboard(() => {
    clipboardTick.value += 1
  })
  window.addEventListener('keydown', onPanelKeydown, true)
})

onBeforeUnmount(() => {
  clearHoverHide()
  if (tipRaf) cancelAnimationFrame(tipRaf)
  unsubClipboard?.()
  window.removeEventListener('keydown', onPanelKeydown, true)
})

watch(
  () => store.conversations,
  (list) => {
    if (store.workspaceId) convMap[store.workspaceId] = [...list]
  },
  { deep: true },
)

function isExpanded(id: string) {
  return expandedIds.value.has(id)
}

function showsAll(id: string) {
  return showAllIds.value.has(id)
}

function basename(path: string) {
  const parts = path.replace(/[\\/]+$/, '').split(/[\\/]/)
  return parts[parts.length - 1] || path
}

function isSsh(ws: Workspace) {
  return (ws.kind || 'local') === 'ssh'
}

function hostKey(ws: Workspace) {
  if (!isSsh(ws)) return 'local'
  const host = ws.ssh_host || 'unknown'
  const port = ws.ssh_port || 22
  const user = ws.ssh_user || ''
  const display = (ws.ssh_display_name || '').trim()
  // Match backend dedupe: named sessions are separate host cards.
  return display ? `ssh:${user}@${host}:${port}/n/${display}` : `ssh:${user}@${host}:${port}`
}

function hostEndpoint(ws: Workspace) {
  const host = ws.ssh_host || 'unknown'
  const port = ws.ssh_port || 22
  const user = ws.ssh_user || ''
  return user ? `${user}@${host}:${port}` : `${host}:${port}`
}

function hostLabel(ws: Workspace) {
  if (!isSsh(ws)) return t('workspace.panel.local')
  const custom = (ws.ssh_display_name || '').trim()
  return custom || hostEndpoint(ws)
}

const workspaceGroups = computed<WorkspaceHostGroup[]>(() => {
  const map = new Map<string, WorkspaceHostGroup>()
  for (const ws of store.recentWorkspaces) {
    const key = hostKey(ws)
    let group = map.get(key)
    if (!group) {
      group = {
        key,
        label: hostLabel(ws),
        kind: isSsh(ws) ? 'ssh' : 'local',
        groupName: isSsh(ws) ? normalizeFolderPath(ws.ssh_group || '') : '',
        workspaces: [],
      }
      map.set(key, group)
    }
    group.workspaces.push(ws)
    if (isSsh(ws)) {
      const custom = (ws.ssh_display_name || '').trim()
      if (custom) group.label = custom
      const g = normalizeFolderPath(ws.ssh_group || '')
      if (g) group.groupName = g
    }
  }
  // Local first, then SSH hosts alphabetically
  return [...map.values()].sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'local' ? -1 : 1
    return a.label.localeCompare(b.label)
  })
})

const localHostGroups = computed(() => workspaceGroups.value.filter((g) => g.kind === 'local'))
const sshHostGroups = computed(() => workspaceGroups.value.filter((g) => g.kind === 'ssh'))

const knownGroupNames = computed(() =>
  collectAllFolderPaths(
    extraGroups.value,
    sshHostGroups.value.map((g) => g.groupName),
  ),
)

const folderForest = computed(() => buildFolderForest(knownGroupNames.value))

const rootSshHosts = computed(() =>
  sshHostGroups.value.filter((g) => !normalizeFolderPath(g.groupName)),
)

function hostsInFolder(path: string) {
  const p = normalizeFolderPath(path)
  return sshHostGroups.value.filter((g) => normalizeFolderPath(g.groupName) === p)
}

function hostCountUnder(path: string) {
  const p = normalizeFolderPath(path)
  if (!p) return rootSshHosts.value.length
  return sshHostGroups.value.filter((g) => isUnderFolder(g.groupName, p)).length
}

const EXPANDED_HOSTS_KEY = 'ca.sshExpandedHosts'
const EXPANDED_FOLDERS_KEY = 'ca.sshExpandedFolders'

function loadExpandedSet(storageKey: string): Set<string> {
  if (typeof localStorage === 'undefined') return new Set()
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.map((x) => String(x || '')).filter(Boolean))
  } catch {
    return new Set()
  }
}

function saveExpandedSet(storageKey: string, set: Set<string>) {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(storageKey, JSON.stringify([...set]))
}

/** Expanded = open. Empty set means all hosts/folders start collapsed. */
const expandedHosts = ref<Set<string>>(loadExpandedSet(EXPANDED_HOSTS_KEY))
const expandedFolders = ref<Set<string>>(loadExpandedSet(EXPANDED_FOLDERS_KEY))

const HOST_DRAG_MIME = 'application/x-code-agent-ssh-host'
const FOLDER_DRAG_MIME = 'application/x-code-agent-ssh-folder'
const dragHostKey = ref<string | null>(null)
const dragFolderPath = ref<string | null>(null)
const dropFolderPath = ref<string | null>(null)
const moving = ref(false)

const folderMenu = ref<{ x: number; y: number; path: string } | null>(null)
const hostMenu = ref<{ x: number; y: number; key: string } | null>(null)
const wsMenu = ref<{ x: number; y: number; wsId: string } | null>(null)
const clipboardTick = ref(0)
const focusHostKey = ref<string | null>(null)
let unsubClipboard: (() => void) | null = null
let pastingHost = false

function persistExpandedHosts() {
  saveExpandedSet(EXPANDED_HOSTS_KEY, expandedHosts.value)
}

function persistExpandedFolders() {
  saveExpandedSet(EXPANDED_FOLDERS_KEY, expandedFolders.value)
}

function isHostOpen(key: string) {
  return expandedHosts.value.has(key)
}

function isFolderOpen(path: string) {
  return expandedFolders.value.has(path)
}

function toggleFolder(path: string) {
  const next = new Set(expandedFolders.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  expandedFolders.value = next
  persistExpandedFolders()
}

function openFolder(path: string) {
  if (!path) return
  if (expandedFolders.value.has(path)) return
  expandedFolders.value = new Set([...expandedFolders.value, path])
  persistExpandedFolders()
}

function rewriteExpandedFolderPaths(from: string, to: string) {
  const f = normalizeFolderPath(from)
  if (!f) return
  const next = new Set<string>()
  for (const p of expandedFolders.value) {
    const rewritten = rewriteFolderPrefix(p, f, to)
    if (rewritten) next.add(rewritten)
  }
  expandedFolders.value = next
  persistExpandedFolders()
}

function forgetExpandedFolderPaths(folder: string) {
  const f = normalizeFolderPath(folder)
  if (!f) return
  expandedFolders.value = new Set(
    [...expandedFolders.value].filter((p) => !isUnderFolder(p, f)),
  )
  persistExpandedFolders()
}

function refreshExtraGroups() {
  extraGroups.value = loadExtraHostGroups()
}

async function patchHostGroup(workspaces: Workspace[], group: string) {
  await Promise.all(
    workspaces.map((ws) =>
      api(`/api/workspaces/${ws.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ ssh_group: group }),
      }),
    ),
  )
}

async function rewriteWorkspaceGroups(from: string, to: string) {
  const f = normalizeFolderPath(from)
  if (!f) return
  const targets = store.recentWorkspaces.filter(
    (ws) => (ws.kind || 'local') === 'ssh' && isUnderFolder(ws.ssh_group || '', f),
  )
  await Promise.all(
    targets.map((ws) =>
      api(`/api/workspaces/${ws.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          ssh_group: rewriteFolderPrefix(ws.ssh_group || '', f, to),
        }),
      }),
    ),
  )
}

async function moveHostToFolder(host: WorkspaceHostGroup, folderPath: string) {
  if (host.kind !== 'ssh' || !host.workspaces.length) return
  const next = normalizeFolderPath(folderPath)
  if (normalizeFolderPath(host.groupName) === next) return
  if (moving.value) return
  moving.value = true
  try {
    await patchHostGroup(host.workspaces, next)
    await store.loadWorkspaces()
    if (next) rememberHostGroup(next)
    refreshExtraGroups()
    openFolder(next)
    toast.info(
      next
        ? t('workspace.panel.movedToFolder', { host: host.label, folder: next })
        : t('workspace.panel.movedToUngrouped', { host: host.label }),
    )
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err)
    toast.error(raw || t('workspace.panel.moveFailed'))
  } finally {
    moving.value = false
  }
}

async function moveFolderToParent(fromPath: string, destParent: string) {
  const from = normalizeFolderPath(fromPath)
  if (!from) return
  const leaf = folderLeafName(from)
  const dest = normalizeFolderPath(destParent)
  if (isSameOrDescendant(from, dest)) {
    toast.warning(t('workspace.panel.cannotMoveIntoSelf'))
    return
  }
  const to = childFolderPath(dest, leaf)
  if (to === from) return
  if (knownGroupNames.value.includes(to) && to !== from) {
    toast.warning(t('workspace.panel.newGroupExists'))
    return
  }
  if (moving.value) return
  moving.value = true
  try {
    await rewriteWorkspaceGroups(from, to)
    rewriteExtraHostGroups(from, to)
    rewriteExpandedFolderPaths(from, to)
    rememberHostGroup(to)
    await store.loadWorkspaces()
    refreshExtraGroups()
    openFolder(to)
    if (dest) openFolder(dest)
    toast.info(t('workspace.panel.movedFolder', { from, to }))
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err)
    toast.error(raw || t('workspace.panel.moveFailed'))
  } finally {
    moving.value = false
  }
}

function hasTreeDrag(e: DragEvent) {
  const types = e.dataTransfer?.types
  return (
    Boolean(dragHostKey.value) ||
    Boolean(dragFolderPath.value) ||
    (types != null && ([...types].includes(HOST_DRAG_MIME) || [...types].includes(FOLDER_DRAG_MIME)))
  )
}

function onHostDragStart(group: WorkspaceHostGroup, e: DragEvent) {
  if (group.kind !== 'ssh') {
    e.preventDefault()
    return
  }
  // setData must stay sync; defer reactive UI so the drag source is not re-rendered mid-dragstart
  if (e.dataTransfer) {
    e.dataTransfer.setData(HOST_DRAG_MIME, group.key)
    e.dataTransfer.setData('text/plain', group.key)
    e.dataTransfer.effectAllowed = 'move'
  }
  requestAnimationFrame(() => {
    clearTip()
    folderMenu.value = null
    hostMenu.value = null
    wsMenu.value = null
    dragHostKey.value = group.key
    dragFolderPath.value = null
    dropFolderPath.value = null
  })
}

function onHostDragEnd() {
  dragHostKey.value = null
  dropFolderPath.value = null
}

function onFolderDragStart(path: string, e: DragEvent) {
  if (e.dataTransfer) {
    e.dataTransfer.setData(FOLDER_DRAG_MIME, path)
    e.dataTransfer.setData('text/plain', path)
    e.dataTransfer.effectAllowed = 'move'
  }
  requestAnimationFrame(() => {
    clearTip()
    folderMenu.value = null
    hostMenu.value = null
    wsMenu.value = null
    dragFolderPath.value = path
    dragHostKey.value = null
    dropFolderPath.value = null
  })
}

function onFolderDragEnd() {
  dragFolderPath.value = null
  dropFolderPath.value = null
}

function onFolderDragOver(path: string, e: DragEvent) {
  if (!hasTreeDrag(e)) return
  if (dragFolderPath.value && isSameOrDescendant(dragFolderPath.value, path)) {
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'none'
    return
  }
  e.preventDefault()
  e.stopPropagation()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  dropFolderPath.value = path
  openFolder(path)
}

function onFolderDragLeave(path: string, e: DragEvent) {
  const related = e.relatedTarget as Node | null
  const current = e.currentTarget as HTMLElement | null
  if (current && related && current.contains(related)) return
  if (dropFolderPath.value === path) dropFolderPath.value = null
}

async function onFolderDrop(path: string, e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  const hostKey = e.dataTransfer?.getData(HOST_DRAG_MIME) || dragHostKey.value
  const folderKey = e.dataTransfer?.getData(FOLDER_DRAG_MIME) || dragFolderPath.value
  dropFolderPath.value = null
  dragHostKey.value = null
  dragFolderPath.value = null
  const dest = normalizeFolderPath(path)
  if (folderKey) {
    await moveFolderToParent(folderKey, dest)
    return
  }
  if (hostKey) {
    const host = workspaceGroups.value.find((g) => g.key === hostKey && g.kind === 'ssh')
    if (host) await moveHostToFolder(host, dest)
  }
}

async function onRootDrop(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  const hostKey = e.dataTransfer?.getData(HOST_DRAG_MIME) || dragHostKey.value
  const folderKey = e.dataTransfer?.getData(FOLDER_DRAG_MIME) || dragFolderPath.value
  dropFolderPath.value = null
  dragHostKey.value = null
  dragFolderPath.value = null
  if (folderKey) {
    await moveFolderToParent(folderKey, '')
    return
  }
  if (hostKey) {
    const host = workspaceGroups.value.find((g) => g.key === hostKey && g.kind === 'ssh')
    if (host) await moveHostToFolder(host, '')
  }
}

function onRootDragOver(e: DragEvent) {
  if (!hasTreeDrag(e)) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  dropFolderPath.value = ''
}

async function createHostGroup(parentPath = '') {
  const raw = await store.askPrompt({
    title: parentPath ? t('workspace.panel.ctxNewSubfolder') : t('workspace.panel.newGroup'),
    summary: parentPath ? t('workspace.panel.newSubfolderPrompt') : t('workspace.panel.newGroupPrompt'),
    label: t('workspace.panel.folderName'),
    placeholder: t('workspace.panel.folderNamePlaceholder'),
    confirmLabel: t('common.create'),
  })
  if (raw == null) return
  const name = sanitizeFolderName(raw)
  if (!name) return
  const full = childFolderPath(parentPath, name)
  if (knownGroupNames.value.includes(full)) {
    toast.info(t('workspace.panel.newGroupExists'))
    openFolder(full)
    return
  }
  rememberHostGroup(full)
  refreshExtraGroups()
  openFolder(full)
  if (parentPath) openFolder(parentPath)
}

async function renameFolder(path: string) {
  const from = normalizeFolderPath(path)
  if (!from) return
  const raw = await store.askPrompt({
    title: t('workspace.panel.ctxRename'),
    summary: t('workspace.panel.renameFolderPrompt'),
    label: t('workspace.panel.folderName'),
    defaultValue: folderLeafName(from),
    confirmLabel: t('common.rename'),
  })
  if (raw == null) return
  const name = sanitizeFolderName(raw)
  if (!name) return
  const to = childFolderPath(parentFolderPath(from), name)
  if (to === from) return
  if (knownGroupNames.value.includes(to)) {
    toast.warning(t('workspace.panel.newGroupExists'))
    return
  }
  if (moving.value) return
  moving.value = true
  try {
    await rewriteWorkspaceGroups(from, to)
    rewriteExtraHostGroups(from, to)
    rewriteExpandedFolderPaths(from, to)
    rememberHostGroup(to)
    await store.loadWorkspaces()
    refreshExtraGroups()
    openFolder(to)
    toast.info(t('workspace.panel.renamedFolder', { from, to }))
  } catch (err) {
    const rawErr = err instanceof Error ? err.message : String(err)
    toast.error(rawErr || t('workspace.panel.moveFailed'))
  } finally {
    moving.value = false
  }
}

function copyFolder(path: string) {
  const from = normalizeFolderPath(path)
  if (!from) return
  const parent = parentFolderPath(from)
  const copyName = `${folderLeafName(from)} ${t('workspace.panel.copySuffix')}`
  const to = uniqueSiblingPath(parent, copyName, knownGroupNames.value)
  copyExtraHostSubtree(from, to)
  refreshExtraGroups()
  openFolder(to)
  if (parent) openFolder(parent)
  toast.info(t('workspace.panel.copiedFolder', { from, to }))
}

async function deleteFolder(path: string) {
  const from = normalizeFolderPath(path)
  if (!from) return
  const hosts = sshHostGroups.value.filter((g) => isUnderFolder(g.groupName, from))
  const parent = parentFolderPath(from)
  const ok = await store.askConfirm({
    title: t('workspace.panel.ctxDelete'),
    summary: hosts.length
      ? t('workspace.panel.deleteFolderConfirmHosts', { folder: from, n: hosts.length })
      : t('workspace.panel.deleteFolderConfirm', { folder: from }),
    confirmLabel: t('common.delete'),
    danger: true,
  })
  if (!ok) return
  if (moving.value) return
  moving.value = true
  try {
    if (hosts.length) {
      await Promise.all(hosts.map((h) => patchHostGroup(h.workspaces, parent)))
      await store.loadWorkspaces()
    }
    forgetHostGroup(from)
    forgetExpandedFolderPaths(from)
    refreshExtraGroups()
    if (parent) openFolder(parent)
    toast.info(t('workspace.panel.deletedFolder', { folder: from }))
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err)
    toast.error(raw || t('workspace.panel.moveFailed'))
  } finally {
    moving.value = false
  }
}

function startAddInFolder(folderPath: string) {
  openPrefill.value = {
    mode: 'ssh',
    lockMode: false,
    ssh_group: normalizeFolderPath(folderPath) || undefined,
  }
  showOpen.value = true
}

function openFolderMenu(path: string, e: MouseEvent) {
  hostMenu.value = null
  wsMenu.value = null
  folderMenu.value = { x: e.clientX, y: e.clientY, path }
}

function openUngroupedMenu(e: MouseEvent) {
  // Don't steal host/workspace row context menus.
  const target = e.target as HTMLElement | null
  if (target?.closest('.host-row, .ws-row, .host-block')) return
  hostMenu.value = null
  wsMenu.value = null
  folderMenu.value = { x: e.clientX, y: e.clientY, path: '' }
}

const folderMenuItems = computed((): ContextMenuItem[] => {
  void clipboardTick.value
  if (!folderMenu.value) return []
  const path = folderMenu.value.path
  // Ungrouped / root paste target — only add/paste.
  if (!path) {
    return [
      { id: 'new-session', label: t('workspace.panel.ctxAddRemoteWorkspace'), icon: 'plus' },
      { id: 'paste', label: t('workspace.panel.ctxPaste'), icon: 'paste', disabled: !hasSshHostClipboard() },
    ]
  }
  return [
    { id: 'new-session', label: t('workspace.panel.ctxAddRemoteWorkspace'), icon: 'plus' },
    { id: 'new-subfolder', label: t('workspace.panel.ctxNewSubfolder'), icon: 'folder-plus' },
    { id: 'paste', label: t('workspace.panel.ctxPaste'), icon: 'paste', disabled: !hasSshHostClipboard() },
    { id: 'sep1', separator: true },
    { id: 'rename', label: t('workspace.panel.ctxRename'), icon: 'pencil' },
    { id: 'copy', label: t('workspace.panel.ctxCopy'), icon: 'copy' },
    { id: 'sep2', separator: true },
    { id: 'delete', label: t('workspace.panel.ctxDelete'), icon: 'trash', danger: true },
  ]
})

function onFolderMenuSelect(id: string) {
  const path = folderMenu.value?.path
  folderMenu.value = null
  if (path == null) return
  if (id === 'new-session') startAddInFolder(path)
  else if (id === 'new-subfolder') void createHostGroup(path)
  else if (id === 'paste') void pasteHostClone(path)
  else if (id === 'rename') void renameFolder(path)
  else if (id === 'copy') copyFolder(path)
  else if (id === 'delete') void deleteFolder(path)
}

function findHostGroup(key: string | null | undefined) {
  if (!key) return null
  return workspaceGroups.value.find((g) => g.key === key) || null
}

function findWorkspace(id: string | null | undefined) {
  if (!id) return null
  return store.recentWorkspaces.find((w) => w.id === id) || null
}

function openHostMenu(group: WorkspaceHostGroup, e: MouseEvent) {
  folderMenu.value = null
  wsMenu.value = null
  focusHostKey.value = group.key
  hostMenu.value = { x: e.clientX, y: e.clientY, key: group.key }
}

function openWsMenu(ws: Workspace, e: MouseEvent) {
  folderMenu.value = null
  hostMenu.value = null
  wsMenu.value = { x: e.clientX, y: e.clientY, wsId: ws.id }
}

const hostMenuItems = computed((): ContextMenuItem[] => {
  void clipboardTick.value
  const group = findHostGroup(hostMenu.value?.key)
  if (!group) return []
  if (group.kind !== 'ssh') {
    return [
      { id: 'add-workspace', label: t('workspace.panel.addLocalWorkspace'), icon: 'plus' },
      { id: 'details', label: t('workspace.panel.ctxDetails'), icon: 'eye' },
    ]
  }
  return [
    { id: 'add-workspace', label: t('workspace.panel.ctxAddRemoteWorkspace'), icon: 'plus' },
    { id: 'edit', label: t('workspace.panel.ctxEdit'), icon: 'pencil' },
    { id: 'copy', label: t('workspace.panel.ctxCopyHost'), icon: 'copy' },
    { id: 'paste', label: t('workspace.panel.ctxPaste'), icon: 'paste', disabled: !hasSshHostClipboard() },
    { id: 'details', label: t('workspace.panel.ctxDetails'), icon: 'eye' },
    { id: 'sep1', separator: true },
    { id: 'delete', label: t('workspace.panel.ctxDeleteHost'), icon: 'trash', danger: true },
  ]
})

const wsMenuItems = computed((): ContextMenuItem[] => {
  const ws = findWorkspace(wsMenu.value?.wsId)
  if (!ws) return []
  const items: ContextMenuItem[] = []
  if (ws.id !== store.workspaceId) {
    items.push({ id: 'open', label: t('workspace.panel.open'), icon: 'folder' })
  }
  items.push({ id: 'new-session', label: t('workspace.panel.newSession'), icon: 'plus' })
  if (isSsh(ws)) {
    items.push({ id: 'copy-host', label: t('workspace.panel.ctxCopyHost'), icon: 'copy' })
  }
  items.push({ id: 'details', label: t('workspace.panel.ctxDetails'), icon: 'eye' })
  items.push({ id: 'sep1', separator: true })
  items.push({ id: 'remove', label: t('workspace.panel.removeWorkspace'), icon: 'trash', danger: true })
  return items
})

function copyHostGroup(group: WorkspaceHostGroup) {
  if (group.kind !== 'ssh') return
  const sample = group.workspaces[0]
  if (!sample) return
  focusHostKey.value = group.key
  setSshHostClipboard({
    ssh_display_name: (sample.ssh_display_name || '').trim() || undefined,
    ssh_group: (sample.ssh_group || group.groupName || '').trim() || undefined,
    ssh_host: sample.ssh_host || '',
    ssh_port: sample.ssh_port || 22,
    ssh_user: sample.ssh_user || '',
    reuse_ssh_from: sample.id,
    label: group.label,
    workspaces: group.workspaces.map((ws) => ({
      root_path: ws.root_path,
      name: ws.name || undefined,
    })),
  })
  toast.info(t('workspace.panel.copiedHost', { host: group.label || formatSshEndpoint(sample) }))
}

async function pasteHostClone(folderPath: string | null) {
  const clip = getSshHostClipboard()
  if (!clip?.ssh_host || !clip.workspaces.length) return
  if (pastingHost) return
  pastingHost = true
  const targetGroup = normalizeFolderPath(folderPath || '') || undefined
  const display = uniqueHostCopyName(
    clip.label || clip.ssh_display_name || formatSshEndpoint(clip),
    sshHostGroups.value.map((g) => g.label),
    t('workspace.panel.copySuffix'),
  )
  try {
    let lastId: string | null = null
    for (const item of clip.workspaces) {
      const ws = await store.addSshWorkspace(
        {
          root_path: item.root_path,
          name: item.name,
          ssh_display_name: display,
          ssh_group: targetGroup ?? clip.ssh_group,
          ssh_host: clip.ssh_host,
          ssh_port: clip.ssh_port,
          ssh_user: clip.ssh_user,
          reuse_ssh_from: clip.reuse_ssh_from,
        },
        { select: false },
      )
      lastId = ws.id
    }
    await store.loadWorkspaces()
    if (lastId) {
      const created = store.recentWorkspaces.find((w) => w.id === lastId)
      if (created) {
        focusHostKey.value = hostKey(created)
        const next = new Set(expandedHosts.value)
        next.add(focusHostKey.value)
        expandedHosts.value = next
        persistExpandedHosts()
      }
    }
    toast.info(t('workspace.panel.pastedHost', { host: display, n: clip.workspaces.length }))
  } catch (err) {
    toast.error(err instanceof Error ? err.message : t('workspace.panel.pasteHostFailed'))
  } finally {
    pastingHost = false
  }
}

function onPanelKeydown(e: KeyboardEvent) {
  const target = e.target as HTMLElement | null
  if (!target) return
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) return
  const mod = e.ctrlKey || e.metaKey
  if (!mod || e.altKey) return
  const key = e.key.toLowerCase()
  if (key === 'c') {
    const group = findHostGroup(focusHostKey.value)
    if (group?.kind !== 'ssh') return
    e.preventDefault()
    e.stopPropagation()
    copyHostGroup(group)
  } else if (key === 'v') {
    if (!hasSshHostClipboard()) return
    // Prefer pasting while a host/folder context is active.
    const inPanel = Boolean(
      target.closest?.('.workspace-panel') ||
        document.activeElement?.closest?.('.workspace-panel') ||
        hostMenu.value ||
        folderMenu.value ||
        focusHostKey.value,
    )
    if (!inPanel) return
    e.preventDefault()
    e.stopPropagation()
    const group = findHostGroup(focusHostKey.value)
    void pasteHostClone(group?.groupName || null)
  }
}

function showHostDetails(group: WorkspaceHostGroup, x: number, y: number) {
  clearHoverHide()
  hoverId.value = null
  hoverHostKey.value = group.key
  scheduleTipPlace({ left: x, top: y, right: x, bottom: y, width: 0, height: 0, x, y, toJSON() { return {} } } as DOMRect, () => hoverHostKey.value === group.key)
}

function showWsDetails(ws: Workspace, x: number, y: number) {
  clearHoverHide()
  hoverHostKey.value = null
  hoverId.value = ws.id
  scheduleTipPlace({ left: x, top: y, right: x, bottom: y, width: 0, height: 0, x, y, toJSON() { return {} } } as DOMRect, () => hoverId.value === ws.id)
}

async function deleteHostGroup(group: WorkspaceHostGroup) {
  const n = group.workspaces.length
  if (!n) return
  const ok = await store.askConfirm({
    title: t('workspace.panel.ctxDeleteHost'),
    summary:
      n === 1
        ? t('workspace.panel.deleteHostConfirmOne', { host: group.label })
        : t('workspace.panel.deleteHostConfirm', { host: group.label, n }),
    confirmLabel: t('workspace.panel.ctxDeleteHost'),
    danger: true,
  })
  if (!ok) return
  for (const ws of [...group.workspaces]) {
    try {
      await store.removeWorkspace(ws.id)
      const next = new Set(expandedIds.value)
      next.delete(ws.id)
      expandedIds.value = next
      delete convMap[ws.id]
      delete loading[ws.id]
      delete errors[ws.id]
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
      break
    }
  }
}

function onHostMenuSelect(id: string) {
  const group = findHostGroup(hostMenu.value?.key)
  const x = hostMenu.value?.x ?? 0
  const y = hostMenu.value?.y ?? 0
  hostMenu.value = null
  if (!group) return
  const fake = { preventDefault() {}, stopPropagation() {} } as MouseEvent
  if (id === 'add-workspace') startAddWorkspace(group, fake)
  else if (id === 'edit') startEditHost(group, fake)
  else if (id === 'copy') copyHostGroup(group)
  else if (id === 'paste') void pasteHostClone(group.groupName || null)
  else if (id === 'details') showHostDetails(group, x, y)
  else if (id === 'delete') void deleteHostGroup(group)
}

function onWsMenuSelect(id: string) {
  const ws = findWorkspace(wsMenu.value?.wsId)
  const x = wsMenu.value?.x ?? 0
  const y = wsMenu.value?.y ?? 0
  wsMenu.value = null
  if (!ws) return
  const fake = { preventDefault() {}, stopPropagation() {} } as MouseEvent
  if (id === 'open') void openWorkspace(ws, fake)
  else if (id === 'new-session') void newSession(ws, fake)
  else if (id === 'copy-host') {
    const group = workspaceGroups.value.find((g) => g.workspaces.some((w) => w.id === ws.id))
    if (group) copyHostGroup(group)
  } else if (id === 'details') showWsDetails(ws, x, y)
  else if (id === 'remove') void removeWorkspace(ws, fake)
}

function onHostEdited() {
  editingHost.value = null
  for (const g of workspaceGroups.value) {
    if (g.groupName) rememberHostGroup(g.groupName)
  }
  refreshExtraGroups()
}

function toggleHost(key: string) {
  focusHostKey.value = key
  const next = new Set(expandedHosts.value)
  const opening = !next.has(key)
  if (opening) {
    next.add(key)
  } else {
    next.delete(key)
    const group = workspaceGroups.value.find((g) => g.key === key)
    if (group?.workspaces.length) {
      const expanded = new Set(expandedIds.value)
      const showAll = new Set(showAllIds.value)
      for (const ws of group.workspaces) {
        expanded.delete(ws.id)
        showAll.delete(ws.id)
      }
      expandedIds.value = expanded
      showAllIds.value = showAll
    }
  }
  expandedHosts.value = next
  persistExpandedHosts()
}

function isHostActive(group: WorkspaceHostGroup) {
  return group.workspaces.some((ws) => ws.id === store.workspaceId)
}

function hostBlockProps(group: WorkspaceHostGroup, nested = false) {
  return {
    group,
    open: isHostOpen(group.key),
    active: isHostActive(group),
    draggableHost: group.kind === 'ssh',
    nested,
    creatingId: creatingId.value,
    switchingId: switchingId.value,
    removingId: removingId.value,
    openingId: openingId.value,
    editingId: editingId.value,
    editingTitle: editingTitle.value,
    previewLimit: PREVIEW_LIMIT,
    isExpanded,
    showsAll,
    sortedConvs,
    visibleConvs,
    hiddenCount,
    loading,
    errors,
    statusByKey: statusByKey.value,
    isPinned: (wsId: string, id: string) => pins.isPinnedIn(wsId, id),
    turnCount,
  }
}

const hoverWorkspace = computed(() =>
  store.recentWorkspaces.find((w) => w.id === hoverId.value) || null,
)

const hoverHost = computed(() =>
  workspaceGroups.value.find((g) => g.key === hoverHostKey.value) || null,
)

function clearHoverHide() {
  if (hoverHideTimer) {
    window.clearTimeout(hoverHideTimer)
    hoverHideTimer = 0
  }
}

function clearTip() {
  hoverId.value = null
  hoverHostKey.value = null
  hoverReady.value = false
}

function placeTip(anchor: DOMRect) {
  const el = tipEl.value
  const width = el?.offsetWidth || 280
  const height = el?.offsetHeight || 120
  const gap = 10
  const margin = 8
  let left = anchor.right + gap
  if (left + width > window.innerWidth - margin) {
    left = Math.max(margin, anchor.left - width - gap)
  }
  let top = anchor.top
  if (top + height > window.innerHeight - margin) {
    top = Math.max(margin, window.innerHeight - height - margin)
  }
  tipStyle.value = {
    position: 'fixed',
    left: `${left}px`,
    top: `${top}px`,
    zIndex: '13000',
  }
  hoverReady.value = true
}

function scheduleTipPlace(anchor: DOMRect, stillValid: () => boolean) {
  hoverReady.value = false
  void nextTick(() => {
    if (tipRaf) cancelAnimationFrame(tipRaf)
    tipRaf = requestAnimationFrame(() => {
      tipRaf = 0
      if (!stillValid()) return
      placeTip(anchor)
    })
  })
}

function showTip(ws: Workspace, e: MouseEvent) {
  clearHoverHide()
  const row = (e.currentTarget as HTMLElement | null)?.closest('.ws-row') as HTMLElement | null
  const anchor = (row || (e.currentTarget as HTMLElement)).getBoundingClientRect()
  hoverHostKey.value = null
  hoverId.value = ws.id
  scheduleTipPlace(anchor, () => hoverId.value === ws.id)
}

function showHostTip(group: WorkspaceHostGroup, e: MouseEvent) {
  clearHoverHide()
  const row = (e.currentTarget as HTMLElement | null)?.closest('.host-row') as HTMLElement | null
  const anchor = (row || (e.currentTarget as HTMLElement)).getBoundingClientRect()
  hoverId.value = null
  hoverHostKey.value = group.key
  scheduleTipPlace(anchor, () => hoverHostKey.value === group.key)
}

function scheduleHideTip() {
  clearHoverHide()
  hoverHideTimer = window.setTimeout(() => {
    clearTip()
    hoverHideTimer = 0
  }, 120)
}

function keepTip() {
  clearHoverHide()
}

function hostSample(group: WorkspaceHostGroup) {
  return group.workspaces[0] || null
}

function hostWorkspaceNames(group: WorkspaceHostGroup) {
  return group.workspaces.map((ws) => ws.name || basename(ws.root_path))
}

function hostLastOpened(group: WorkspaceHostGroup) {
  let best: string | null = null
  for (const ws of group.workspaces) {
    const t = ws.last_opened_at
    if (!t) continue
    if (!best || t > best) best = t
  }
  return best
}

function sessionCountLabel(wsId: string) {
  if (!(wsId in convMap)) return null
  return sortedConvs(wsId).length
}

async function setExpanded(id: string, open: boolean) {
  const next = new Set(expandedIds.value)
  if (open) next.add(id)
  else {
    next.delete(id)
    const all = new Set(showAllIds.value)
    all.delete(id)
    showAllIds.value = all
  }
  expandedIds.value = next
  if (open) await loadConvs(id)
}

async function toggleExpand(id: string) {
  await setExpanded(id, !isExpanded(id))
}

async function expandAllSessions() {
  expandedFolders.value = new Set(knownGroupNames.value)
  expandedHosts.value = new Set(workspaceGroups.value.map((g) => g.key))
  persistExpandedFolders()
  persistExpandedHosts()
  const currentId = store.workspaceId
  if (currentId) await setExpanded(currentId, true)
}

function collapseAllSessions() {
  expandedFolders.value = new Set()
  expandedHosts.value = new Set()
  persistExpandedFolders()
  persistExpandedHosts()
  expandedIds.value = new Set()
  showAllIds.value = new Set()
}

function toggleShowAll(id: string) {
  const next = new Set(showAllIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  showAllIds.value = next
}

async function loadConvs(wsId: string, force = false) {
  // Reuse cached list on re-expand; current workspace stays in sync via store.conversations watch.
  if (!force && wsId in convMap && !errors[wsId]) return
  if (loading[wsId]) return
  loading[wsId] = true
  errors[wsId] = ''
  try {
    convMap[wsId] = await api<Conversation[]>(`/api/workspaces/${wsId}/conversations`)
  } catch (err) {
    errors[wsId] = err instanceof Error ? err.message : String(err)
  } finally {
    loading[wsId] = false
  }
}

function sortedConvs(wsId: string) {
  void pinTick.value
  return pins.sortByPinIn(wsId, convMap[wsId] || [])
}

function visibleConvs(wsId: string) {
  const list = sortedConvs(wsId)
  if (showsAll(wsId) || list.length <= PREVIEW_LIMIT) return list
  return list.slice(0, PREVIEW_LIMIT)
}

function hiddenCount(wsId: string) {
  const n = sortedConvs(wsId).length - PREVIEW_LIMIT
  return n > 0 && !showsAll(wsId) ? n : 0
}

async function openWorkspace(ws: Workspace, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (switchingId.value || ws.id === store.workspaceId) return
  switchingId.value = ws.id
  try {
    await store.selectWorkspace(ws.id, { openExplorer: false })
    await setExpanded(ws.id, true)
  } finally {
    switchingId.value = null
  }
}

function startEditHost(group: WorkspaceHostGroup, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (group.kind !== 'ssh') return
  editingHost.value = group
}

function startAddWorkspace(group: WorkspaceHostGroup, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (group.kind === 'ssh') {
    const sample = group.workspaces[0]
    openPrefill.value = {
      mode: 'ssh',
      lockMode: true,
      ssh_display_name: (sample?.ssh_display_name || '').trim() || undefined,
      ssh_group: (sample?.ssh_group || group.groupName || '').trim() || undefined,
      ssh_host: sample?.ssh_host || '',
      ssh_port: sample?.ssh_port || 22,
      ssh_user: sample?.ssh_user || '',
      reuse_ssh_from: sample?.id,
    }
  } else {
    openPrefill.value = { mode: 'local', lockMode: true }
  }
  showOpen.value = true
}

function closeOpenDialog() {
  showOpen.value = false
  openPrefill.value = null
}

async function removeWorkspace(ws: Workspace, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (removingId.value) return
  const name = ws.name || basename(ws.root_path)
  const ok = await store.askConfirm({
    title: t('workspace.panel.removeTitle'),
    summary: t('workspace.panel.removeSummary', { name }),
    confirmLabel: t('workspace.panel.removeConfirm'),
    danger: true,
  })
  if (!ok) return
  removingId.value = ws.id
  try {
    await store.removeWorkspace(ws.id)
    const next = new Set(expandedIds.value)
    next.delete(ws.id)
    expandedIds.value = next
    delete convMap[ws.id]
    delete loading[ws.id]
    delete errors[ws.id]
  } finally {
    removingId.value = null
  }
}

async function newSession(ws: Workspace, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (creatingId.value) return
  creatingId.value = ws.id
  try {
    if (store.workspaceId !== ws.id) {
      await store.selectWorkspace(ws.id, { openExplorer: false })
    }
    await setExpanded(ws.id, true)
    await store.newChat()
    window.dispatchEvent(new Event('ca-focus-agent'))
  } finally {
    creatingId.value = null
  }
}

async function openConv(ws: Workspace, conv: Conversation) {
  if (openingId.value || editingId.value === conv.id) return
  openingId.value = conv.id
  try {
    if (store.workspaceId !== ws.id) {
      try {
        await store.selectWorkspace(ws.id, {
          openExplorer: false,
          conversationId: conv.id,
        })
      } catch (err) {
        // open() may have already flipped workspaceId; still try to open the chat.
        if (store.workspaceId !== ws.id) throw err
      }
    }
    // Always land on the clicked conversation. selectWorkspace restores a preferred
    // id, but a partial failure used to leave the previous workspace's messages up
    // until a second click.
    if (store.workspaceId === ws.id && store.conversationId !== conv.id) {
      await store.openConversation(conv.id)
    }
    window.dispatchEvent(new Event('ca-focus-agent'))
  } catch (err) {
    toast.error(err instanceof Error ? err.message : t('workspace.panel.openFailed'))
  } finally {
    openingId.value = null
  }
}

function turnCount(wsId: string, item: Conversation) {
  if (wsId === store.workspaceId && item.id === store.conversationId) {
    return store.messages.filter((m) => m.role === 'user').length
  }
  return item.turn_count ?? 0
}

function sessionStatus(wsId: string, item: Conversation): { label: string; tone: string; icon: string } | null {
  let kind: 'approval' | 'queued' | 'running' | null = null
  if (wsId === store.workspaceId && item.id === store.conversationId) {
    if (store.pendingApprovals.length) kind = 'approval'
    else if (store.isRunBusy()) kind = store.runStatus === 'queued' ? 'queued' : 'running'
  } else if (item.awaiting_approval) {
    kind = 'approval'
  } else if (item.active_run_id) {
    if (item.run_status === 'queued') kind = 'queued'
    else if (!item.run_status || item.run_status === 'running') kind = 'running'
  }
  if (!kind) return null
  if (kind === 'approval') {
    return { label: t('workspace.panel.statusApproval'), tone: 'confirm', icon: 'shield' }
  }
  if (kind === 'queued') {
    return { label: t('workspace.panel.statusQueued'), tone: 'queued', icon: 'clock' }
  }
  return { label: t('workspace.panel.statusRunning'), tone: 'running', icon: 'loader' }
}

const statusByKey = computed(() => {
  const map = new Map<string, { label: string; tone: string; icon: string }>()
  for (const ws of store.recentWorkspaces) {
    if (!isExpanded(ws.id)) continue
    for (const item of convMap[ws.id] || []) {
      const status = sessionStatus(ws.id, item)
      if (status) map.set(`${ws.id}:${item.id}`, status)
    }
  }
  return map
})

function onTogglePin(wsId: string, id: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  pins.toggleIn(wsId, id)
  pinTick.value += 1
}

async function onDelete(wsId: string, id: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  if (editingId.value === id) cancelRename()
  if (pins.isPinnedIn(wsId, id)) pins.toggleIn(wsId, id)
  pinTick.value += 1

  if (wsId === store.workspaceId) {
    await store.deleteConversation(id)
    return
  }

  await api(`/api/conversations/${id}`, { method: 'DELETE' })
  convMap[wsId] = (convMap[wsId] || []).filter((c) => c.id !== id)
}

async function onArchive(wsId: string, conv: Conversation, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  const next = !conv.archived
  if (wsId === store.workspaceId) {
    await store.archiveConversation(conv.id, next)
  } else {
    await api(`/api/conversations/${conv.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ archived: next }),
    })
  }
  if (next) {
    convMap[wsId] = (convMap[wsId] || []).filter((c) => c.id !== conv.id)
  }
}

function startRename(item: Conversation, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  editingId.value = item.id
  editingTitle.value = item.title
  void nextTick(() => {
    const el = document.querySelector<HTMLInputElement>('.conv-rename-input')
    el?.focus()
    el?.select()
  })
}

async function commitRename(wsId: string, id: string) {
  if (editingId.value !== id) return
  const title = editingTitle.value.trim()
  editingId.value = null
  editingTitle.value = ''
  if (!title) return

  if (wsId === store.workspaceId) {
    await store.renameConversation(id, title)
    return
  }

  const row = (convMap[wsId] || []).find((c) => c.id === id)
  if (!row || row.title === title) return
  await api(`/api/conversations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
  convMap[wsId] = (convMap[wsId] || []).map((c) => (c.id === id ? { ...c, title } : c))
}

function cancelRename() {
  editingId.value = null
  editingTitle.value = ''
}

function onRenameKeydown(wsId: string, id: string, e: KeyboardEvent) {
  e.stopPropagation()
  if (e.key === 'Enter') {
    e.preventDefault()
    void commitRename(wsId, id)
    return
  }
  if (e.key === 'Escape') {
    e.preventDefault()
    cancelRename()
  }
}
</script>

<template>
  <div class="panel-shell workspace-panel panel-chromeless" tabindex="-1">
    <header class="ws-head">
      <span class="ws-head-title">{{ t('workspace.panel.title') }}</span>
      <div class="ws-head-actions">
        <button
          type="button"
          class="ws-head-btn icon"
          :title="t('workspace.panel.collapseHosts')"
          :disabled="!store.recentWorkspaces.length && !extraGroups.length"
          @click="collapseAllSessions"
        >
          <AppIcon name="collapse-all" :size="14" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ws-head-btn icon"
          :title="t('workspace.panel.expandHosts')"
          :disabled="!store.recentWorkspaces.length && !extraGroups.length"
          @click="expandAllSessions"
        >
          <AppIcon name="expand-all" :size="14" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ws-head-btn icon"
          :title="t('workspace.panel.newGroup')"
          @click="createHostGroup()"
        >
          <AppIcon name="folder-plus" :size="14" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ws-head-btn"
          :title="t('workspace.panel.openWorkspace')"
          @click="openPrefill = null; showOpen = true"
        >
          <AppIcon name="plus" :size="14" :stroke-width="1.75" />
          <span>{{ t('workspace.panel.open') }}</span>
        </button>
      </div>
    </header>

    <div
      class="workspace-body"
      :class="{ 'drop-root': dropFolderPath === '' && (dragHostKey || dragFolderPath) }"
      @dragover="onRootDragOver"
      @drop="onRootDrop"
    >
      <p v-if="!store.recentWorkspaces.length && !extraGroups.length" class="empty">{{ t('workspace.panel.empty') }}</p>

      <WorkspaceHostBlock
        v-for="group in localHostGroups"
        :key="group.key"
        v-bind="hostBlockProps(group)"
        @toggle-host="toggleHost(group.key)"
        @edit-host="startEditHost(group, $event)"
        @add-workspace="startAddWorkspace(group, $event)"
        @host-contextmenu="openHostMenu(group, $event)"
        @ws-contextmenu="(ws, e) => openWsMenu(ws, e)"
        @host-tip="showHostTip(group, $event)"
        @host-tip-hide="scheduleHideTip"
        @ws-tip="(ws, e) => showTip(ws, e)"
        @ws-tip-hide="scheduleHideTip"
        @toggle-expand="toggleExpand"
        @new-session="(ws, e) => newSession(ws, e)"
        @open-workspace="(ws, e) => openWorkspace(ws, e)"
        @remove-workspace="(ws, e) => removeWorkspace(ws, e)"
        @retry-convs="(id) => loadConvs(id, true)"
        @open-conv="(ws, conv) => openConv(ws, conv)"
        @update:editing-title="editingTitle = $event"
        @rename-keydown="(wsId, id, e) => onRenameKeydown(wsId, id, e)"
        @rename-blur="(wsId, id) => commitRename(wsId, id)"
        @start-rename="(conv, e) => startRename(conv, e)"
        @toggle-pin="(wsId, id, e) => onTogglePin(wsId, id, e)"
        @archive="(wsId, conv, e) => onArchive(wsId, conv, e)"
        @delete-conv="(wsId, id, e) => onDelete(wsId, id, e)"
        @toggle-show-all="toggleShowAll"
      />

      <div v-if="folderForest.length || rootSshHosts.length" class="folder-tree">
        <WorkspaceFolderNode
          v-for="node in folderForest"
          :key="node.path"
          :node="node"
          :open="isFolderOpen(node.path)"
          :drop-over="dropFolderPath === node.path"
          :dragging="dragFolderPath === node.path"
          :host-count="hostCountUnder(node.path)"
          :child-open="isFolderOpen"
          :child-drop-over="(p) => dropFolderPath === p"
          :child-dragging="(p) => dragFolderPath === p"
          :host-count-of="hostCountUnder"
          @toggle="toggleFolder"
          @contextmenu="openFolderMenu"
          @dragstart="onFolderDragStart"
          @dragend="onFolderDragEnd"
          @dragover="onFolderDragOver"
          @dragleave="onFolderDragLeave"
          @drop="onFolderDrop"
        >
          <template #default="{ folderPath }">
            <p
              v-if="!hostsInFolder(folderPath).length && (dragHostKey || dragFolderPath)"
              class="hint group-empty"
            >
              {{ t('workspace.panel.dropHostHere') }}
            </p>
            <WorkspaceHostBlock
              v-for="group in hostsInFolder(folderPath)"
              :key="group.key"
              v-bind="hostBlockProps(group, true)"
              @toggle-host="toggleHost(group.key)"
              @edit-host="startEditHost(group, $event)"
              @add-workspace="startAddWorkspace(group, $event)"
              @host-contextmenu="openHostMenu(group, $event)"
              @ws-contextmenu="(ws, e) => openWsMenu(ws, e)"
              @dragstart="onHostDragStart(group, $event)"
              @dragend="onHostDragEnd"
              @host-tip="showHostTip(group, $event)"
              @host-tip-hide="scheduleHideTip"
              @ws-tip="(ws, e) => showTip(ws, e)"
              @ws-tip-hide="scheduleHideTip"
              @toggle-expand="toggleExpand"
              @new-session="(ws, e) => newSession(ws, e)"
              @open-workspace="(ws, e) => openWorkspace(ws, e)"
              @remove-workspace="(ws, e) => removeWorkspace(ws, e)"
              @retry-convs="(id) => loadConvs(id, true)"
              @open-conv="(ws, conv) => openConv(ws, conv)"
              @update:editing-title="editingTitle = $event"
              @rename-keydown="(wsId, id, e) => onRenameKeydown(wsId, id, e)"
              @rename-blur="(wsId, id) => commitRename(wsId, id)"
              @start-rename="(conv, e) => startRename(conv, e)"
              @toggle-pin="(wsId, id, e) => onTogglePin(wsId, id, e)"
              @archive="(wsId, conv, e) => onArchive(wsId, conv, e)"
              @delete-conv="(wsId, id, e) => onDelete(wsId, id, e)"
              @toggle-show-all="toggleShowAll"
            />
          </template>
        </WorkspaceFolderNode>

        <div
          v-if="rootSshHosts.length"
          class="ungrouped-root"
          :class="{ 'drop-over': dropFolderPath === '' && (dragHostKey || dragFolderPath) }"
          @dragover="onRootDragOver"
          @drop="onRootDrop"
          @contextmenu.prevent="openUngroupedMenu"
        >
          <div class="ungrouped-label">{{ t('workspace.panel.ungrouped') }}</div>
          <WorkspaceHostBlock
            v-for="group in rootSshHosts"
            :key="group.key"
            v-bind="hostBlockProps(group, true)"
            @toggle-host="toggleHost(group.key)"
            @edit-host="startEditHost(group, $event)"
            @add-workspace="startAddWorkspace(group, $event)"
            @host-contextmenu="openHostMenu(group, $event)"
            @ws-contextmenu="(ws, e) => openWsMenu(ws, e)"
            @dragstart="onHostDragStart(group, $event)"
            @dragend="onHostDragEnd"
            @host-tip="showHostTip(group, $event)"
            @host-tip-hide="scheduleHideTip"
            @ws-tip="(ws, e) => showTip(ws, e)"
            @ws-tip-hide="scheduleHideTip"
            @toggle-expand="toggleExpand"
            @new-session="(ws, e) => newSession(ws, e)"
            @open-workspace="(ws, e) => openWorkspace(ws, e)"
            @remove-workspace="(ws, e) => removeWorkspace(ws, e)"
            @retry-convs="(id) => loadConvs(id, true)"
            @open-conv="(ws, conv) => openConv(ws, conv)"
            @update:editing-title="editingTitle = $event"
            @rename-keydown="(wsId, id, e) => onRenameKeydown(wsId, id, e)"
            @rename-blur="(wsId, id) => commitRename(wsId, id)"
            @start-rename="(conv, e) => startRename(conv, e)"
            @toggle-pin="(wsId, id, e) => onTogglePin(wsId, id, e)"
            @archive="(wsId, conv, e) => onArchive(wsId, conv, e)"
            @delete-conv="(wsId, id, e) => onDelete(wsId, id, e)"
            @toggle-show-all="toggleShowAll"
          />
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="hoverHost || hoverWorkspace"
        ref="tipEl"
        class="ws-tip"
        :class="{ ready: hoverReady }"
        :style="tipStyle"
        role="tooltip"
        @mouseenter="keepTip"
        @mouseleave="scheduleHideTip"
      >
        <template v-if="hoverHost">
          <div class="ws-tip-head">
            <AppIcon
              class="ws-tip-icon"
              :class="{ 'is-ssh': hoverHost.kind === 'ssh' }"
              :name="hoverHost.kind === 'ssh' ? 'globe' : 'folder'"
              :size="15"
              :stroke-width="1.75"
            />
            <div class="ws-tip-titles">
              <strong>{{ hoverHost.label }}</strong>
              <span class="ws-tip-badge" :class="hoverHost.kind === 'ssh' ? 'remote' : 'local'">
                {{ hoverHost.kind === 'ssh' ? t('workspace.panel.remote') : t('workspace.panel.local') }}
              </span>
              <span v-if="isHostActive(hoverHost)" class="ws-tip-badge">{{ t('workspace.panel.current') }}</span>
            </div>
          </div>
          <dl class="ws-tip-meta">
            <div v-if="hoverHost.kind === 'ssh' && hostSample(hoverHost)">
              <dt>{{ t('workspace.panel.host') }}</dt>
              <dd class="mono">{{ hostEndpoint(hostSample(hoverHost)!) }}</dd>
            </div>
            <div>
              <dt>{{ t('workspace.panel.workspaces') }}</dt>
              <dd>{{ t('workspace.panel.count', { n: hoverHost.workspaces.length }) }}</dd>
            </div>
            <div v-if="hostWorkspaceNames(hoverHost).length">
              <dt>{{ t('workspace.panel.dirs') }}</dt>
              <dd class="ws-tip-list" :title="hostWorkspaceNames(hoverHost).join('\n')">
                {{ hostWorkspaceNames(hoverHost).slice(0, 6).join('、') }}
                <template v-if="hostWorkspaceNames(hoverHost).length > 6">
                  {{ t('workspace.panel.dirsMore', { n: hostWorkspaceNames(hoverHost).length }) }}
                </template>
              </dd>
            </div>
            <div v-if="hostLastOpened(hoverHost)">
              <dt>{{ t('workspace.panel.lastOpened') }}</dt>
              <dd>{{ formatWorkspaceOpenedAt(hostLastOpened(hoverHost)!) }}</dd>
            </div>
          </dl>
        </template>
        <template v-else-if="hoverWorkspace">
          <div class="ws-tip-head">
            <AppIcon
              class="ws-tip-icon"
              :name="isSsh(hoverWorkspace) ? 'globe' : 'folder'"
              :size="15"
              :stroke-width="1.75"
            />
            <div class="ws-tip-titles">
              <strong>{{ hoverWorkspace.name || basename(hoverWorkspace.root_path) }}</strong>
              <span v-if="isSsh(hoverWorkspace)" class="ws-tip-badge remote">{{ t('workspace.panel.remote') }}</span>
              <span v-if="hoverWorkspace.id === store.workspaceId" class="ws-tip-badge">{{ t('workspace.panel.current') }}</span>
            </div>
          </div>
          <dl class="ws-tip-meta">
            <div v-if="isSsh(hoverWorkspace)">
              <dt>{{ t('workspace.panel.host') }}</dt>
              <dd class="mono">{{ hostEndpoint(hoverWorkspace) }}</dd>
            </div>
            <div>
              <dt>{{ t('workspace.panel.path') }}</dt>
              <dd class="mono" :title="hoverWorkspace.display_path || hoverWorkspace.root_path">
                {{ hoverWorkspace.display_path || hoverWorkspace.root_path }}
              </dd>
            </div>
            <div v-if="hoverWorkspace.last_opened_at">
              <dt>{{ t('workspace.panel.lastOpened') }}</dt>
              <dd>{{ formatWorkspaceOpenedAt(hoverWorkspace.last_opened_at) }}</dd>
            </div>
            <div v-if="hoverWorkspace.created_at">
              <dt>{{ t('workspace.panel.created') }}</dt>
              <dd>{{ formatRelativeTime(hoverWorkspace.created_at) }}</dd>
            </div>
            <div v-if="sessionCountLabel(hoverWorkspace.id) != null">
              <dt>{{ t('workspace.panel.sessions') }}</dt>
              <dd>{{ t('workspace.panel.count', { n: sessionCountLabel(hoverWorkspace.id) }) }}</dd>
            </div>
          </dl>
        </template>
      </div>
    </Teleport>

    <WorkspaceSwitch
      v-if="showOpen"
      :prefill="openPrefill"
      @close="closeOpenDialog"
    />
    <WorkspaceEditDialog
      v-if="editingHost"
      :workspaces="editingHost.workspaces"
      :label="editingHost.label"
      :known-groups="knownGroupNames"
      @close="onHostEdited"
    />
    <ContextMenu
      v-if="folderMenu"
      :x="folderMenu.x"
      :y="folderMenu.y"
      :items="folderMenuItems"
      @select="onFolderMenuSelect"
      @close="folderMenu = null"
    />
    <ContextMenu
      v-if="hostMenu"
      :x="hostMenu.x"
      :y="hostMenu.y"
      :items="hostMenuItems"
      @select="onHostMenuSelect"
      @close="hostMenu = null"
    />
    <ContextMenu
      v-if="wsMenu"
      :x="wsMenu.x"
      :y="wsMenu.y"
      :items="wsMenuItems"
      @select="onWsMenuSelect"
      @close="wsMenu = null"
    />
  </div>
</template>

<style scoped>

.workspace-panel {
  background: var(--sidebar-bg);
}

.ws-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 4px 8px;
  flex-shrink: 0;
}

.ws-head-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.ws-head-actions {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.ws-head-btn {
  height: 22px;
  padding: 0 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.ws-head-btn.icon {
  width: 22px;
  min-width: 22px;
  padding: 0;
  justify-content: center;
}

.ws-head-btn:hover:not(:disabled) {
  background: var(--code-bg);
  color: var(--text-h);
}

.ws-head-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.workspace-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px 8px 12px;
}


.workspace-body.drop-root {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 35%, transparent);
  background: color-mix(in srgb, var(--primary) 4%, transparent);
}

.folder-tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ungrouped-root {
  margin-top: 6px;
  padding: 4px 0 2px;
  border-radius: 8px;
  transition: background 0.12s ease, box-shadow 0.12s ease;
}

.ungrouped-root.drop-over {
  background: color-mix(in srgb, var(--primary) 8%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 35%, transparent);
}

.ungrouped-label {
  margin: 2px 8px 6px;
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.group-empty {
  margin: 0 10px 10px;
  padding: 6px 8px;
  font-size: 11px;
}

.empty,
.hint {
  margin: 8px 6px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.45;
}

.hint.err {
  color: var(--error-text);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.hint-retry {
  border: 0;
  border-radius: 5px;
  padding: 2px 8px;
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  color: var(--primary);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.hint-retry:hover {
  background: color-mix(in srgb, var(--primary) 18%, transparent);
}

</style>

<style scoped>
.ws-tip {
  width: min(320px, calc(100vw - 16px));
  padding: 10px 12px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: var(--dropdown-shadow);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}
.ws-tip.ready {
  opacity: 1;
  pointer-events: auto;
}
html[data-theme='dark'] .ws-tip {
  box-shadow: var(--dropdown-shadow-dark);
}
.ws-tip-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}
.ws-tip-icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--primary);
}
.ws-tip-icon.is-ssh {
  color: #0284c7;
}
.ws-tip-list {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: normal;
  line-height: 1.4;
}
.ws-tip-titles {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.ws-tip-titles strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
}
.ws-tip-badge {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 10px;
  font-weight: 600;
}
.ws-tip-badge.local {
  background: color-mix(in srgb, var(--text-muted) 16%, transparent);
  color: var(--text-secondary);
}
.ws-tip-badge.remote {
  background: color-mix(in srgb, var(--primary) 16%, transparent);
  color: var(--primary);
}
.ws-tip-meta {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ws-tip-meta > div {
  display: grid;
  grid-template-columns: 4.5em minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}
.ws-tip-meta dt {
  margin: 0;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  line-height: 1.45;
}
.ws-tip-meta dd {
  margin: 0;
  font-size: 12px;
  color: var(--text);
  line-height: 1.45;
  word-break: break-all;
}
.ws-tip-meta dd.mono {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-secondary);
}
</style>
