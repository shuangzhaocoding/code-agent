<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useAppStore, type FsItem } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import ExplorerTreeNode from '@/panels/ExplorerTreeNode.vue'

const store = useAppStore()
const menu = ref<{ x: number; y: number; item: FsItem | null } | null>(null)
const prompt = ref<{ kind: 'file' | 'dir' | 'rename'; dir: string; from?: string; value: string } | null>(null)
const promptEl = ref<HTMLInputElement | null>(null)
const error = ref('')
const renamingPath = ref<string | null>(null)

function closeMenu() {
  menu.value = null
}

function onContext(e: MouseEvent, item: FsItem | null) {
  e.preventDefault()
  e.stopPropagation()
  menu.value = { x: e.clientX, y: e.clientY, item }
}

function targetDir() {
  const item = menu.value?.item
  if (!item) return ''
  return item.is_dir ? item.path : store.parentPath(item.path)
}

function startCreate(kind: 'file' | 'dir') {
  const dir = targetDir()
  closeMenu()
  prompt.value = { kind, dir, value: kind === 'dir' ? 'untitled' : 'untitled.txt' }
  error.value = ''
  nextTick(() => promptEl.value?.select())
}

function startRename() {
  const item = menu.value?.item
  if (!item) return
  closeMenu()
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
  if (!trimmed) return '名称不能为空'
  if (/[\\/]/.test(trimmed) || trimmed === '.' || trimmed === '..') return '名称不合法'
  return ''
}

async function confirmPrompt() {
  if (!prompt.value) return
  const msg = validName(prompt.value.value)
  if (msg) {
    error.value = msg
    return
  }
  const rel = store.joinPath(prompt.value.dir, prompt.value.value.trim())
  try {
    if (prompt.value.kind === 'rename' && prompt.value.from) {
      await store.renameEntry(prompt.value.from, rel)
    } else {
      await store.createEntry(rel, prompt.value.kind)
    }
    prompt.value = null
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

async function onDelete() {
  const item = menu.value?.item
  if (!item) return
  closeMenu()
  const ok = await store.askConfirm({
    title: '删除确认',
    summary: `确定删除 ${item.path}？此操作不可撤销。`,
    confirmLabel: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await store.deleteEntry(item.path)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

function onGlobalClick() {
  closeMenu()
}

onMounted(() => window.addEventListener('click', onGlobalClick))
onUnmounted(() => window.removeEventListener('click', onGlobalClick))
</script>

<template>
  <div class="panel-shell panel-chromeless" @contextmenu="onContext($event, null)">
    <button type="button" class="tree-refresh icon-btn icon-btn-ghost" title="刷新" @click="store.refreshTree()">
      <AppIcon name="refresh" :size="14" />
    </button>
    <form v-if="prompt" class="prompt" @submit.prevent="confirmPrompt">
      <input
        ref="promptEl"
        v-model="prompt.value"
        class="field-control"
        :placeholder="prompt.kind === 'dir' ? '目录名' : '文件名'"
        @keydown.esc="prompt = null"
      />
      <button type="submit" class="btn btn-primary">确定</button>
      <button type="button" class="btn" @click="prompt = null">取消</button>
    </form>
    <p v-if="error" class="err">{{ error }}</p>
    <div class="tree">
      <ExplorerTreeNode
        v-for="item in store.childrenOf('')"
        :key="item.path"
        :item="item"
        :depth="0"
        :renaming-path="renamingPath"
        @context="onContext"
        @start-rename="(p) => renamingPath = p"
        @commit-rename="commitInlineRename"
        @cancel-rename="cancelInlineRename"
      />
    </div>
    <div v-if="menu" class="ctx" :style="{ left: menu.x + 'px', top: menu.y + 'px' }" @click.stop>
      <button type="button" @click="startCreate('file')">新建文件</button>
      <button type="button" @click="startCreate('dir')">新建目录</button>
      <button v-if="menu.item" type="button" @click="startRename">重命名</button>
      <button v-if="menu.item" type="button" class="danger" @click="onDelete">删除</button>
    </div>
  </div>
</template>

<style scoped>
.panel-shell { overflow: hidden; position: relative; background: var(--sidebar-bg); }
.tree-refresh {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 2;
  width: 28px;
  height: 28px;
}
.prompt {
  display: flex;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
.prompt .field-control { flex: 1; min-width: 0; }
.btn { height: 28px; padding: 0 10px; font-size: 12px; }
.err {
  margin: 0;
  padding: 6px 12px;
  color: var(--danger);
  font-size: 12px;
}
.tree {
  flex: 1;
  overflow: auto;
  padding: 36px 0 12px;
}
.icon-btn { width: 28px; height: 28px; }
.ctx {
  position: fixed;
  z-index: 80;
  min-width: 140px;
  padding: 6px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: none;
  display: flex;
  flex-direction: column;
}
.ctx button {
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--text);
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.ctx button:hover { background: var(--bg-muted); }
.ctx button.danger { color: var(--danger); }
</style>
