<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore, type FsItem } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import ExplorerTreeNode from '@/panels/ExplorerTreeNode.vue'
import ExplorerCreateRow from '@/panels/ExplorerCreateRow.vue'

const { t } = useI18n()
const store = useAppStore()
const menu = ref<{ x: number; y: number; item: FsItem | null } | null>(null)
const creating = ref<{ kind: 'file' | 'dir'; dir: string; value: string; id: number } | null>(null)
const error = ref('')
const renamingPath = ref<string | null>(null)
const selectedItem = ref<FsItem | null>(null)
let createSeq = 0

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
  selectedItem.value = item
  menu.value = { x: e.clientX, y: e.clientY, item }
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
    await store.deleteEntry(item.path)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

function onDownload() {
  const item = menu.value?.item
  if (!item || item.is_dir || !store.workspaceId) return
  closeMenu()
  const url =
    `/api/workspaces/${store.workspaceId}/file/raw` +
    `?path=${encodeURIComponent(item.path)}&download=1`
  const a = document.createElement('a')
  a.href = url
  a.download = item.name
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

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

onMounted(() => window.addEventListener('click', onGlobalClick))
onUnmounted(() => window.removeEventListener('click', onGlobalClick))
</script>

<template>
  <div class="panel-shell panel-chromeless" @contextmenu="onContext($event, null)">
    <div class="explorer-bar">
      <span class="explorer-title" :title="workspaceTitle">{{ workspaceTitle }}</span>
      <div class="explorer-actions">
        <button type="button" class="icon-btn icon-btn-ghost" :title="t('explorer.newFile')" @click.stop="startCreate('file')">
          <AppIcon name="file-plus" :size="14" />
        </button>
        <button type="button" class="icon-btn icon-btn-ghost" :title="t('explorer.newDir')" @click.stop="startCreate('dir')">
          <AppIcon name="folder-plus" :size="14" />
        </button>
        <button type="button" class="icon-btn icon-btn-ghost" :title="t('common.refresh')" @click.stop="store.refreshTree()">
          <AppIcon name="refresh" :size="14" />
        </button>
        <button type="button" class="icon-btn icon-btn-ghost" :title="t('common.collapseAll')" @click.stop="store.collapseAllDirs()">
          <AppIcon name="collapse-all" :size="14" />
        </button>
        <button type="button" class="icon-btn icon-btn-ghost" :title="t('common.expandAll')" @click.stop="store.expandAllDirs()">
          <AppIcon name="expand-all" :size="14" />
        </button>
      </div>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
    <div class="tree">
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
    <div v-if="menu" class="ctx" :style="{ left: menu.x + 'px', top: menu.y + 'px' }" @click.stop>
      <button type="button" @click="startCreate('file')">
        <AppIcon class="ctx-ico" name="file-plus" :size="15" />
        <span>{{ t('explorer.newFile') }}</span>
      </button>
      <button type="button" @click="startCreate('dir')">
        <AppIcon class="ctx-ico" name="folder-plus" :size="15" />
        <span>{{ t('explorer.newDir') }}</span>
      </button>
      <button v-if="menu.item && !menu.item.is_dir" type="button" @click="onDownload">
        <AppIcon class="ctx-ico" name="download" :size="15" />
        <span>{{ t('common.download') }}</span>
      </button>
      <button v-if="menu.item" type="button" @click="startRename">
        <AppIcon class="ctx-ico" name="pencil" :size="15" />
        <span>{{ t('common.rename') }}</span>
      </button>
      <button v-if="menu.item" type="button" class="danger" @click="onDelete">
        <AppIcon class="ctx-ico" name="trash" :size="15" />
        <span>{{ t('common.delete') }}</span>
      </button>
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
  </div>
</template>

<style scoped>
.panel-shell { overflow: hidden; position: relative; background: var(--sidebar-bg); }
.explorer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 32px;
  padding: 6px 10px;
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
  gap: 8px;
  flex-shrink: 0;
}
.icon-btn { width: 28px; height: 28px; flex-shrink: 0; }
.err {
  margin: 0;
  padding: 6px 12px;
  color: var(--danger);
  font-size: 12px;
}
.tree {
  flex: 1;
  overflow: auto;
  padding: 0 0 12px;
}
.ctx {
  position: fixed;
  z-index: 80;
  min-width: 168px;
  padding: 6px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
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
  color: var(--text);
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.ctx-ico {
  flex: 0 0 16px;
  width: 16px;
  color: color-mix(in srgb, var(--text) 62%, transparent);
}
.ctx button:hover { background: var(--bg-muted); color: var(--text-h); }
.ctx button:hover .ctx-ico { color: var(--text-h); }
.ctx button.danger { color: var(--danger); }
.ctx button.danger .ctx-ico { color: var(--danger); }
</style>
