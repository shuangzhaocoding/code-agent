<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore, type FsItem } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import FileTreeIcon from '@/components/FileTreeIcon.vue'
import ExplorerTreeNode from '@/panels/ExplorerTreeNode.vue'
import ExplorerCreateRow from '@/panels/ExplorerCreateRow.vue'
import {
  explorerDragKey,
  FS_DRAG_MIME,
  isOsFileDrag,
  type FsDragPayload,
} from '@/panels/explorerDrag'
import { collectDataTransferFiles } from '@/utils/fsDrop'

const { t } = useI18n()
const store = useAppStore()
const menu = ref<{ x: number; y: number; item: FsItem | null } | null>(null)
const menuEl = ref<HTMLElement | null>(null)
const menuPos = ref({ left: 0, top: 0 })
const creating = ref<{ kind: 'file' | 'dir'; dir: string; value: string; id: number } | null>(null)
const error = ref('')
const renamingPath = ref<string | null>(null)
const selectedItem = ref<FsItem | null>(null)
const uploadInput = ref<HTMLInputElement | null>(null)
const uploadDirInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadRatio = ref(0)
let uploadDestDir = ''
let createSeq = 0

const dragSrc = ref<FsDragPayload | null>(null)
const dropHoverPath = ref<string | null>(null)
const externalDrop = ref(false)
let dropDestDir: string | null = null

function canDropTo(destDir: string, src: FsDragPayload | null = dragSrc.value) {
  if (!src) return false
  if (store.parentPath(src.path) === destDir) return false
  if (src.is_dir && (destDir === src.path || destDir.startsWith(`${src.path}/`))) return false
  return true
}

function resolveDestDir(item: FsItem) {
  return item.is_dir ? item.path : store.parentPath(item.path)
}

function beginDrag(item: FsItem) {
  clearItemTip()
  dragSrc.value = { path: item.path, is_dir: item.is_dir }
  dropHoverPath.value = null
  dropDestDir = null
  externalDrop.value = false
}

function endDrag() {
  dragSrc.value = null
  dropHoverPath.value = null
  dropDestDir = null
  externalDrop.value = false
}

function setDropHover(path: string | null, destDir: string | null, opts?: { external?: boolean }) {
  if (!opts?.external && destDir !== null && !canDropTo(destDir)) {
    dropHoverPath.value = null
    dropDestDir = null
    externalDrop.value = false
    return
  }
  dropHoverPath.value = path
  dropDestDir = destDir
  externalDrop.value = Boolean(opts?.external)
}

async function dropTo(destDir: string) {
  const src = dragSrc.value
  const ok = canDropTo(destDir, src)
  endDrag()
  if (!src || !ok) return
  try {
    await store.moveFsEntry(src.path, destDir, src.is_dir)
    error.value = ''
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    error.value =
      msg.includes('itself') ? t('explorer.cannotMoveIntoSelf') : msg || t('explorer.moveFail')
  }
}

async function dropFiles(destDir: string, files: FileList | File[]) {
  endDrag()
  const list = Array.from(files || []).filter((f) => f && f.name)
  if (!list.length) return
  uploading.value = true
  uploadRatio.value = 0.02
  error.value = ''
  try {
    await store.uploadWorkspaceFiles(destDir, list, (info) => {
      uploadRatio.value = Math.max(0.02, Math.min(1, info.ratio))
    })
    uploadRatio.value = 1
    await new Promise((r) => setTimeout(r, 180))
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('explorer.uploadFail')
  } finally {
    uploading.value = false
    uploadRatio.value = 0
  }
}

async function dropDataTransfer(destDir: string, dt: DataTransfer | null | undefined) {
  try {
    const files = await collectDataTransferFiles(dt)
    await dropFiles(destDir, files)
  } catch (err) {
    endDrag()
    error.value = err instanceof Error ? err.message : t('explorer.uploadFail')
  }
}

provide(explorerDragKey, {
  dragSrc,
  dropHoverPath,
  beginDrag,
  endDrag,
  setDropHover,
  canDropTo,
  resolveDestDir,
  dropTo,
  dropFiles,
  dropDataTransfer,
  showItemTip,
  scheduleHideTip,
})

const tipEl = ref<HTMLElement | null>(null)
const hoverItem = ref<FsItem | null>(null)
const hoverReady = ref(false)
const tipStyle = ref<Record<string, string>>({})
let hoverHideTimer = 0
let tipShowTimer = 0
let tipRaf = 0

function clearHoverHide() {
  if (hoverHideTimer) {
    clearTimeout(hoverHideTimer)
    hoverHideTimer = 0
  }
}

function clearTipShow() {
  if (tipShowTimer) {
    clearTimeout(tipShowTimer)
    tipShowTimer = 0
  }
}

function clearItemTip() {
  clearHoverHide()
  clearTipShow()
  if (tipRaf) {
    cancelAnimationFrame(tipRaf)
    tipRaf = 0
  }
  hoverItem.value = null
  hoverReady.value = false
}

function placeTip(anchor: DOMRect) {
  const el = tipEl.value
  const width = el?.offsetWidth || 300
  const height = el?.offsetHeight || 140
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

function showItemTip(item: FsItem, e: MouseEvent) {
  if (menu.value || dragSrc.value) {
    clearItemTip()
    return
  }
  clearHoverHide()
  clearTipShow()
  const row = (e.currentTarget as HTMLElement | null) || null
  const anchor = row?.getBoundingClientRect()
  if (!anchor) return
  tipShowTimer = window.setTimeout(() => {
    tipShowTimer = 0
    if (menu.value || dragSrc.value) return
    hoverItem.value = item
    scheduleTipPlace(anchor, () => hoverItem.value?.path === item.path)
  }, 260)
}

function scheduleHideTip() {
  clearTipShow()
  clearHoverHide()
  hoverHideTimer = window.setTimeout(() => {
    clearItemTip()
    hoverHideTimer = 0
  }, 120)
}

function keepTip() {
  clearHoverHide()
  clearTipShow()
}

function formatFileSize(bytes: number | null | undefined) {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return null
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let n = bytes / 1024
  let i = 0
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i += 1
  }
  return `${n < 10 && i > 0 ? n.toFixed(1) : Math.round(n)} ${units[i]}`
}

function formatItemMtime(mtime: number | null | undefined) {
  if (mtime == null || !Number.isFinite(mtime) || mtime <= 0) return null
  try {
    return new Date(mtime * 1000).toLocaleString()
  } catch {
    return null
  }
}

const tipAbsPath = computed(() => {
  const item = hoverItem.value
  if (!item) return ''
  return toAbsolutePath(item.path)
})
const tipSizeLabel = computed(() =>
  hoverItem.value && !hoverItem.value.is_dir ? formatFileSize(hoverItem.value.size) : null,
)
const tipMtimeLabel = computed(() =>
  hoverItem.value ? formatItemMtime(hoverItem.value.mtime) : null,
)

function onTreeDragOver(e: DragEvent) {
  const types = e.dataTransfer?.types
  const isOurs = !!dragSrc.value || (types != null && [...types].includes(FS_DRAG_MIME))
  const isFiles = isOsFileDrag(e)
  if (!isOurs && !isFiles) return
  if (isOurs) {
    if (!canDropTo('')) {
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'none'
      return
    }
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
    setDropHover('', '')
    return
  }
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  setDropHover('', '', { external: true })
}

function onTreeDrop(e: DragEvent) {
  const types = e.dataTransfer?.types
  const isOurs = !!dragSrc.value || (types != null && [...types].includes(FS_DRAG_MIME))
  const isFiles = isOsFileDrag(e)
  if (!isOurs && isFiles) {
    e.preventDefault()
    const dest = dropDestDir ?? ''
    void dropDataTransfer(dest, e.dataTransfer)
    return
  }
  if (!isOurs) return
  e.preventDefault()
  void dropTo(dropDestDir ?? '')
}

function startUpload(e?: Event) {
  e?.preventDefault()
  e?.stopPropagation()
  uploadDestDir = targetDir()
  // Open the picker while the click gesture is still valid and the menu button
  // is still in the DOM. Closing the menu first cancels the dialog in Chromium.
  const input = uploadInput.value
  if (!input) return
  input.value = ''
  input.click()
  closeMenu()
}

function startUploadDir(e?: Event) {
  e?.preventDefault()
  e?.stopPropagation()
  uploadDestDir = targetDir()
  const input = uploadDirInput.value
  if (!input) return
  input.value = ''
  input.click()
  closeMenu()
}

async function onUploadInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files ? Array.from(input.files) : []
  input.value = ''
  if (!files.length) return
  await dropFiles(uploadDestDir, files)
}

const workspaceTitle = computed(() => store.workspace?.name || t('panels.workspace'))

const menuDir = computed(() => {
  const item = menu.value?.item
  if (!item) return ''
  return item.is_dir ? item.path : ''
})
const menuFile = computed(() => {
  const item = menu.value?.item
  if (!item || item.is_dir) return ''
  return item.path
})

function closeMenu() {
  menu.value = null
}

function onContext(e: MouseEvent, item: FsItem | null) {
  e.preventDefault()
  e.stopPropagation()
  clearItemTip()
  selectedItem.value = item
  menuPos.value = { left: e.clientX, top: e.clientY }
  menu.value = { x: e.clientX, y: e.clientY, item }
  void nextTick(() => placeMenu())
}

function placeMenu() {
  const el = menuEl.value
  const m = menu.value
  if (!el || !m) return
  const pad = 8
  const w = el.offsetWidth
  const h = el.offsetHeight
  const vw = window.innerWidth
  const vh = window.innerHeight
  let left = m.x
  let top = m.y
  // Prefer flipping above the cursor when there isn't enough room below
  if (top + h > vh - pad) {
    top = Math.max(pad, m.y - h)
  }
  if (top + h > vh - pad) {
    top = Math.max(pad, vh - h - pad)
  }
  if (left + w > vw - pad) {
    left = Math.max(pad, vw - w - pad)
  }
  if (left < pad) left = pad
  if (top < pad) top = pad
  menuPos.value = { left, top }
}

function targetDir() {
  if (menu.value) {
    const item = menu.value.item
    if (!item) return ''
    return item.is_dir ? item.path : store.parentPath(item.path)
  }
  const item = selectedItem.value
  if (item) return item.is_dir ? item.path : store.parentPath(item.path)
  if (store.activePath) return store.parentPath(store.activePath)
  return ''
}

async function startCreate(kind: 'file' | 'dir') {
  const dir = targetDir()
  closeMenu()
  renamingPath.value = null
  error.value = ''
  if (dir) await store.expandDir(dir)
  await nextTick()
  creating.value = {
    kind,
    dir,
    value: '',
    id: ++createSeq,
  }
}

function startRename() {
  const item = menu.value?.item
  if (!item) return
  closeMenu()
  creating.value = null
  renamingPath.value = item.path
}

async function commitInlineRename(from: string, newName: string) {
  const msg = validName(newName)
  if (msg) { error.value = msg; renamingPath.value = null; return }
  const dir = store.parentPath(from)
  const rel = store.joinPath(dir, newName)
  try {
    await store.renameEntry(from, rel)
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
  renamingPath.value = null
}

function cancelInlineRename() {
  renamingPath.value = null
}

function validName(name: string) {
  const trimmed = name.trim()
  if (!trimmed) return t('explorer.emptyName')
  if (/[\\/]/.test(trimmed) || trimmed === '.' || trimmed === '..') return t('explorer.invalidName')
  return ''
}

function cancelCreate() {
  creating.value = null
  error.value = ''
}

function retryCreate() {
  if (!creating.value) return
  creating.value = { ...creating.value, id: ++createSeq }
}

async function commitCreate() {
  if (!creating.value) return
  if (!creating.value.value.trim()) {
    cancelCreate()
    return
  }
  const msg = validName(creating.value.value)
  if (msg) {
    error.value = msg
    retryCreate()
    return
  }
  const rel = store.joinPath(creating.value.dir, creating.value.value.trim())
  const currentId = creating.value.id
  try {
    await store.createEntry(rel, creating.value.kind)
    if (creating.value?.id === currentId) {
      creating.value = null
      error.value = ''
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    if (creating.value?.id === currentId) retryCreate()
  }
}

async function onDelete() {
  const item = menu.value?.item
  if (!item) return
  closeMenu()
  const ok = await store.askConfirm({
    title: t('explorer.deleteTitle'),
    summary: t('explorer.deleteSummary', { path: item.path }),
    confirmLabel: t('common.delete'),
    danger: true,
  })
  if (!ok) return
  try {
    await store.deleteEntry(item.path, item.is_dir)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

function onDownload() {
  const item = menu.value?.item
  if (!item || !store.workspaceId) return
  closeMenu()
  const a = document.createElement('a')
  a.rel = 'noopener'
  if (item.is_dir) {
    const base = item.name || 'folder'
    a.href =
      `/api/workspaces/${store.workspaceId}/archive` +
      `?path=${encodeURIComponent(item.path)}`
    a.download = `${base}.zip`
  } else {
    a.href =
      `/api/workspaces/${store.workspaceId}/file/raw` +
      `?path=${encodeURIComponent(item.path)}&download=1`
    a.download = item.name
  }
  document.body.appendChild(a)
  a.click()
  a.remove()
}

function addToChat() {
  const item = menu.value?.item
  if (!item) return
  closeMenu()
  window.dispatchEvent(new CustomEvent('ca-add-chat-mention', {
    detail: { name: item.name, path: item.path, is_dir: item.is_dir },
  }))
  window.dispatchEvent(new Event('ca-focus-agent'))
}

async function addToNewChat() {
  const item = menu.value?.item
  if (!item) return
  const detail = { name: item.name, path: item.path, is_dir: item.is_dir }
  closeMenu()
  window.dispatchEvent(new Event('ca-focus-agent'))
  try {
    await store.newChat()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    return
  }
  await nextTick()
  await nextTick()
  window.dispatchEvent(new CustomEvent('ca-add-chat-mention', { detail }))
  window.dispatchEvent(new Event('ca-focus-agent'))
}

function toAbsolutePath(rel: string): string {
  const root = (store.workspace?.root_path || '').trim()
  if (!root) return rel
  if (!rel) return root
  const winStyle = /^[A-Za-z]:[\\/]/.test(root) || root.includes('\\')
  const sep = winStyle ? '\\' : '/'
  const normalizedRoot = root.replace(/[\\/]+$/, '')
  const normalizedRel = rel.replace(/^[\\/]+/, '').replace(/[\\/]+/g, sep)
  return `${normalizedRoot}${sep}${normalizedRel}`
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    error.value = t('explorer.copyFail')
  }
}

async function copyRelativePath() {
  const item = menu.value?.item
  if (!item) return
  closeMenu()
  await copyText(item.path)
}

async function copyAbsolutePath() {
  const item = menu.value?.item
  if (!item) return
  closeMenu()
  await copyText(toAbsolutePath(item.path))
}

function onCopyEntry() {
  const item = menu.value?.item
  if (!item) return
  store.setFsClipboard('copy', item)
  closeMenu()
}

function onCutEntry() {
  const item = menu.value?.item
  if (!item) return
  store.setFsClipboard('cut', item)
  closeMenu()
}

async function onPasteEntry() {
  closeMenu()
  const dir = targetDir()
  try {
    await store.pasteFsClipboard(dir)
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

const canPaste = computed(() => {
  const clip = store.fsClipboard
  if (!clip || !store.workspaceId || clip.workspace_id !== store.workspaceId) return false
  const dir = menu.value
    ? menu.value.item
      ? menu.value.item.is_dir
        ? menu.value.item.path
        : store.parentPath(menu.value.item.path)
      : ''
    : targetDir()
  if (clip.is_dir && (dir === clip.path || dir.startsWith(`${clip.path}/`))) return false
  return true
})

function searchIn(path: string) {
  closeMenu()
  store.openSearch(path ? { include: path } : { clearInclude: true, include: null })
}

function excludeFromSearch(path: string) {
  closeMenu()
  if (!path) return
  store.openSearch({ addExclude: path })
}

function onGlobalClick() {
  closeMenu()
}

/** Map editor tab path → workspace-relative tree path (skip outside / revision-only). */
function explorerRelPath(path: string | null | undefined): string | null {
  if (!path) return null
  // Git revision tabs e.g. HEAD:src/foo.ts
  const rev = /^([A-Za-z0-9._-]+):(.+)$/.exec(path)
  if (rev && !/^[A-Za-z]:[\\/]/.test(path)) return rev[2]
  if (path.startsWith('~/') || path.startsWith('/')) return null
  if (/^[A-Za-z]:[\\/]/.test(path)) return null
  return path
}

const treeEl = ref<HTMLElement | null>(null)
let scrollTimer: ReturnType<typeof setTimeout> | null = null

async function scrollTreeToPath(path: string, opts?: { force?: boolean }) {
  const rel = explorerRelPath(path)
  if (!rel || !treeEl.value) return
  await store.revealInTree(rel)
  await nextTick()
  const root = treeEl.value
  const escape =
    typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
      ? CSS.escape(rel)
      : rel.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
  const find = () => root.querySelector(`[data-explorer-path="${escape}"]`) as HTMLElement | null
  let el = find()
  if (!el) {
    await nextTick()
    el = find()
  }
  el?.scrollIntoView({
    block: opts?.force ? 'center' : 'nearest',
    behavior: 'smooth',
  })
}

watch(
  () => store.activePath,
  (path) => {
    if (!path) return
    if (scrollTimer) clearTimeout(scrollTimer)
    // Debounce: tab switches / openPath may set activePath in quick succession
    scrollTimer = setTimeout(() => {
      scrollTimer = null
      void scrollTreeToPath(path)
    }, 50)
  },
)

function onRevealInTree(e: Event) {
  const path = (e as CustomEvent<{ path?: string }>).detail?.path || store.activePath
  if (!path) return
  if (scrollTimer) {
    clearTimeout(scrollTimer)
    scrollTimer = null
  }
  void scrollTreeToPath(path, { force: true })
}

onMounted(() => {
  window.addEventListener('click', onGlobalClick)
  window.addEventListener('ca-reveal-in-tree', onRevealInTree as EventListener)
  window.addEventListener('resize', placeMenu)
})
onUnmounted(() => {
  window.removeEventListener('click', onGlobalClick)
  window.removeEventListener('ca-reveal-in-tree', onRevealInTree as EventListener)
  window.removeEventListener('resize', placeMenu)
  if (scrollTimer) clearTimeout(scrollTimer)
  clearItemTip()
})
</script>

<template>
  <div class="panel-shell panel-chromeless" @contextmenu="onContext($event, null)">
    <div class="explorer-bar">
      <span class="explorer-title" :title="workspaceTitle">{{ workspaceTitle }}</span>
      <div class="explorer-actions">
        <button type="button" class="ghost-icon-btn" :title="t('explorer.newFile')" @click.stop="startCreate('file')">
          <AppIcon name="file-plus" :size="14" :stroke-width="1.75" />
        </button>
        <button type="button" class="ghost-icon-btn" :title="t('explorer.newDir')" @click.stop="startCreate('dir')">
          <AppIcon name="folder-plus" :size="14" :stroke-width="1.75" />
        </button>
        <button type="button" class="ghost-icon-btn" :title="t('common.refresh')" @click.stop="store.refreshTree()">
          <AppIcon name="refresh" :size="14" :stroke-width="1.75" />
        </button>
        <button type="button" class="ghost-icon-btn" :title="t('common.collapseAll')" @click.stop="store.collapseAllDirs()">
          <AppIcon name="collapse-all" :size="14" :stroke-width="1.75" />
        </button>
        <button type="button" class="ghost-icon-btn" :title="t('common.expandAll')" @click.stop="store.expandAllDirs()">
          <AppIcon name="expand-all" :size="14" :stroke-width="1.75" />
        </button>
      </div>
      <div
        v-if="uploading"
        class="upload-progress"
        role="progressbar"
        :aria-valuenow="Math.round(uploadRatio * 100)"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <div class="upload-progress-bar" :style="{ width: `${Math.round(uploadRatio * 1000) / 10}%` }" />
      </div>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
    <div
      ref="treeEl"
      class="tree"
      :class="{
        'drop-over': dropHoverPath === '' && (dragSrc || externalDrop),
      }"
      @dragover="onTreeDragOver"
      @drop="onTreeDrop"
      @scroll.passive="clearItemTip"
    >
      <ExplorerCreateRow
        v-if="creating && creating.dir === ''"
        :key="creating.id"
        :kind="creating.kind"
        :depth="0"
        :dir="''"
        :model-value="creating.value"
        @update:model-value="(v) => creating && (creating.value = v)"
        @commit="commitCreate"
        @cancel="cancelCreate"
      />
      <ExplorerTreeNode
        v-for="item in store.childrenOf('')"
        :key="item.path"
        :item="item"
        :depth="0"
        :renaming-path="renamingPath"
        :creating="creating"
        @context="onContext"
        @select="(item) => selectedItem = item"
        @start-rename="(p) => renamingPath = p"
        @commit-rename="commitInlineRename"
        @cancel-rename="cancelInlineRename"
        @update:creating="(v) => creating && (creating.value = v)"
        @commit-create="commitCreate"
        @cancel-create="cancelCreate"
      />
    </div>
    <div
      v-if="menu"
      ref="menuEl"
      class="ctx"
      :style="{ left: menuPos.left + 'px', top: menuPos.top + 'px' }"
      @click.stop
    >
      <!-- 新建 -->
      <button type="button" @click="startCreate('file')">
        <AppIcon class="ctx-ico" name="file-plus" :size="15" />
        <span>{{ t('explorer.newFile') }}</span>
      </button>
      <button type="button" @click="startCreate('dir')">
        <AppIcon class="ctx-ico" name="folder-plus" :size="15" />
        <span>{{ t('explorer.newDir') }}</span>
      </button>
      <button type="button" @click="startUpload($event)">
        <AppIcon class="ctx-ico" name="upload" :size="15" />
        <span>{{ t('explorer.uploadFile') }}</span>
      </button>
      <button type="button" @click="startUploadDir($event)">
        <AppIcon class="ctx-ico" name="folder" :size="15" />
        <span>{{ t('explorer.uploadDir') }}</span>
      </button>

      <!-- 对话 -->
      <template v-if="menu.item">
        <div class="ctx-sep" />
        <button type="button" @click="addToChat">
          <AppIcon class="ctx-ico" name="chat" :size="15" />
          <span>{{ t('explorer.addToChat') }}</span>
        </button>
        <button type="button" @click="addToNewChat">
          <AppIcon class="ctx-ico" name="chat-plus" :size="15" />
          <span>{{ t('explorer.addToNewChat') }}</span>
        </button>
      </template>

      <!-- 剪贴板：复制 / 剪切 / 粘贴 -->
      <template v-if="menu.item || canPaste">
        <div class="ctx-sep" />
        <button v-if="menu.item" type="button" @click="onCopyEntry">
          <AppIcon class="ctx-ico" name="copy" :size="15" />
          <span>{{ t('common.copy') }}</span>
        </button>
        <button v-if="menu.item" type="button" @click="onCutEntry">
          <AppIcon class="ctx-ico" name="cut" :size="15" />
          <span>{{ t('common.cut') }}</span>
        </button>
        <button v-if="canPaste" type="button" @click="onPasteEntry">
          <AppIcon class="ctx-ico" name="paste" :size="15" />
          <span>{{ t('common.paste') }}</span>
        </button>
      </template>

      <!-- 复制路径 -->
      <template v-if="menu.item">
        <div class="ctx-sep" />
        <button type="button" @click="copyRelativePath">
          <AppIcon class="ctx-ico" name="path-relative" :size="15" />
          <span>{{ t('explorer.copyRelativePath') }}</span>
        </button>
        <button type="button" @click="copyAbsolutePath">
          <AppIcon class="ctx-ico" name="path-absolute" :size="15" />
          <span>{{ t('explorer.copyAbsolutePath') }}</span>
        </button>
      </template>

      <!-- 文件操作 -->
      <template v-if="menu.item">
        <div class="ctx-sep" />
        <button type="button" @click="onDownload">
          <AppIcon class="ctx-ico" name="download" :size="15" />
          <span>{{ menu.item.is_dir ? t('explorer.downloadDir') : t('common.download') }}</span>
        </button>
        <button type="button" @click="startRename">
          <AppIcon class="ctx-ico" name="pencil" :size="15" />
          <span>{{ t('common.rename') }}</span>
        </button>
        <button type="button" class="danger" @click="onDelete">
          <AppIcon class="ctx-ico" name="trash" :size="15" />
          <span>{{ t('common.delete') }}</span>
        </button>
      </template>

      <!-- 搜索 -->
      <div class="ctx-sep" />
      <button v-if="menuDir" type="button" @click="searchIn(menuDir)">
        <AppIcon class="ctx-ico" name="search" :size="15" />
        <span>{{ t('explorer.searchHere') }}</span>
      </button>
      <button v-if="menuDir" type="button" @click="excludeFromSearch(menuDir)">
        <AppIcon class="ctx-ico" name="close" :size="15" />
        <span>{{ t('explorer.excludeDir') }}</span>
      </button>
      <button v-if="menuFile" type="button" @click="searchIn(menuFile)">
        <AppIcon class="ctx-ico" name="search" :size="15" />
        <span>{{ t('explorer.searchFile') }}</span>
      </button>
      <button v-if="menuFile" type="button" @click="excludeFromSearch(menuFile)">
        <AppIcon class="ctx-ico" name="close" :size="15" />
        <span>{{ t('explorer.excludeFile') }}</span>
      </button>
      <button type="button" @click="searchIn('')">
        <AppIcon class="ctx-ico" name="folder" :size="15" />
        <span>{{ t('explorer.searchWorkspace') }}</span>
      </button>
    </div>
    <input
      ref="uploadInput"
      class="explorer-upload-input"
      type="file"
      multiple
      tabindex="-1"
      aria-hidden="true"
      @change="onUploadInputChange"
    />
    <input
      ref="uploadDirInput"
      class="explorer-upload-input"
      type="file"
      multiple
      webkitdirectory
      directory
      tabindex="-1"
      aria-hidden="true"
      @change="onUploadInputChange"
    />

    <Teleport to="body">
      <div
        v-if="hoverItem"
        ref="tipEl"
        class="ex-tip"
        :class="{ ready: hoverReady }"
        :style="tipStyle"
        role="tooltip"
        @mouseenter="keepTip"
        @mouseleave="scheduleHideTip"
      >
        <div class="ex-tip-head">
          <FileTreeIcon
            class="ex-tip-icon"
            :kind="hoverItem.is_dir ? 'dir' : 'file'"
            :path="hoverItem.path"
            :size="16"
          />
          <div class="ex-tip-titles">
            <strong>{{ hoverItem.name }}</strong>
            <span class="ex-tip-badge">{{ hoverItem.is_dir ? t('explorer.kindDir') : t('explorer.kindFile') }}</span>
          </div>
        </div>
        <dl class="ex-tip-meta">
          <div>
            <dt>{{ t('explorer.tipRelativePath') }}</dt>
            <dd class="mono" :title="hoverItem.path">{{ hoverItem.path || '.' }}</dd>
          </div>
          <div v-if="tipAbsPath">
            <dt>{{ t('explorer.tipAbsolutePath') }}</dt>
            <dd class="mono" :title="tipAbsPath">{{ tipAbsPath }}</dd>
          </div>
          <div v-if="tipSizeLabel">
            <dt>{{ t('explorer.tipSize') }}</dt>
            <dd>{{ tipSizeLabel }}</dd>
          </div>
          <div v-if="tipMtimeLabel">
            <dt>{{ t('explorer.tipModified') }}</dt>
            <dd>{{ tipMtimeLabel }}</dd>
          </div>
        </dl>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.panel-shell { overflow: hidden; position: relative; background: var(--sidebar-bg); }
.explorer-bar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 28px;
  padding: 4px 8px;
  flex-shrink: 0;
}
.explorer-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}
.explorer-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.explorer-actions .icon-btn {
  width: 22px;
  height: 22px;
  min-width: 22px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-secondary);
}
.explorer-actions .icon-btn:hover:not(:disabled) {
  background: var(--code-bg);
  color: var(--text-h);
  opacity: 1;
  border-color: transparent;
}
.err {
  margin: 0;
  padding: 6px 12px;
  color: var(--danger);
  font-size: 12px;
}
.upload-progress {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2px;
  background: color-mix(in srgb, var(--primary) 16%, transparent);
  overflow: hidden;
  pointer-events: none;
  z-index: 2;
}
.upload-progress-bar {
  height: 100%;
  background: var(--primary);
  transition: width 0.12s linear;
}
.explorer-upload-input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
  opacity: 0;
  pointer-events: none;
}
.tree {
  flex: 1;
  overflow: auto;
  padding: 0 0 12px;
  min-height: 48px;
  outline: 2px solid transparent;
  outline-offset: -2px;
  transition: outline-color 0.12s ease, background-color 0.12s ease;
}
.tree.drop-over {
  outline-color: color-mix(in srgb, var(--primary) 55%, transparent);
  background: color-mix(in srgb, var(--primary) 8%, transparent);
}
.ctx {
  position: fixed;
  z-index: 80;
  min-width: 168px;
  max-height: min(70vh, calc(100vh - 16px));
  overflow-x: hidden;
  overflow-y: auto;
  padding: 6px;
  background: var(--panel-bg);
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--dropdown-shadow);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ctx-sep {
  height: 1px;
  margin: 4px 6px;
  background: var(--border);
}
.ctx button {
  display: flex;
  align-items: center;
  gap: 8px;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--text-h);
  min-height: 34px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: background-color 0.12s ease;
}
.ctx-ico {
  flex: 0 0 16px;
  width: 16px;
  color: color-mix(in srgb, var(--text) 62%, transparent);
}
.ctx button:hover { background: var(--code-bg); color: var(--text-h); }
.ctx button:hover .ctx-ico { color: var(--text-h); }
.ctx button.danger { color: var(--danger); }
.ctx button.danger .ctx-ico { color: var(--danger); }
</style>

<style scoped>
.ex-tip {
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
.ex-tip.ready {
  opacity: 1;
  pointer-events: auto;
}
html[data-theme='dark'] .ex-tip {
  box-shadow: var(--dropdown-shadow-dark);
}
.ex-tip-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}
.ex-tip-icon {
  flex-shrink: 0;
  margin-top: 1px;
}
.ex-tip-titles {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.ex-tip-titles strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
}
.ex-tip-badge {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--text-muted) 16%, transparent);
  color: var(--text-secondary);
  font-size: 10px;
  font-weight: 600;
}
.ex-tip-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
}
.ex-tip-meta > div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}
.ex-tip-meta dt {
  margin: 0;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
}
.ex-tip-meta dd {
  margin: 0;
  font-size: 12px;
  color: var(--text);
  line-height: 1.4;
  word-break: break-all;
}
.ex-tip-meta dd.mono {
  font-family: var(--mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace);
  font-size: 11px;
}
</style>
