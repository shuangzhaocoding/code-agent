<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { useWorkspaceBrowse } from '@/composables/useWorkspaceBrowse'
import AppIcon from '@/components/AppIcon.vue'
import WorkspaceMkdirRow from '@/components/WorkspaceMkdirRow.vue'

const emit = defineEmits<{ close: [] }>()
const store = useAppStore()
const { browsing, path, error, creating, createValue, createKey, dirs, browse, startCreate, cancelCreate, commitCreate, errMessage } = useWorkspaceBrowse()

onMounted(async () => {
  await store.loadWorkspaces()
  await browse(store.workspace?.root_path || '~')
})

async function openPath() {
  if (!path.value) return
  error.value = ''
  try {
    await store.addWorkspace(path.value)
    emit('close')
  } catch (err) {
    error.value = errMessage(err)
  }
}

async function openRecent(id: string) {
  await store.selectWorkspace(id)
  emit('close')
}

const recents = computed(() => store.workspaces)
</script>

<template>
  <div class="mask" @click.self="emit('close')">
    <div class="page-panel sheet" role="dialog" aria-label="打开工作区">
      <header>
        <h1 class="page-panel__title">打开工作空间</h1>
        <button type="button" class="icon-btn" title="关闭" @click="emit('close')">×</button>
      </header>
      <p class="page-panel__lead">选择本地目录，或从最近工作空间进入。</p>
      <div class="search-box">
        <AppIcon class="search-box-icon" name="folder" :size="18" />
        <input v-model="path" placeholder="/path/to/project" @keydown.enter="openPath" />
        <button type="button" class="search-box-btn" @click="openPath">打开</button>
      </div>
      <p v-if="error" class="err">{{ error }}</p>
      <div class="nested-list browse">
        <div class="crumbs">
          <button type="button" class="btn btn-ghost" @click="browse(browsing?.parent || '~')">上级</button>
          <button type="button" class="btn btn-ghost" @click="startCreate">新建文件夹</button>
          <span>{{ browsing?.path }}</span>
        </div>
        <ul class="dirs">
          <li v-if="creating">
            <WorkspaceMkdirRow
              :key="createKey"
              :model-value="createValue"
              @update:model-value="createValue = $event"
              @commit="commitCreate"
              @cancel="cancelCreate"
            />
          </li>
          <li v-for="item in dirs" :key="item.path">
            <button type="button" class="menu-item" @click="browse(item.path)">
              <AppIcon name="folder" :size="15" />
              {{ item.name }}
            </button>
          </li>
        </ul>
      </div>
      <section v-if="recents.length" class="recents">
        <h2 class="page-panel__title">最近打开</h2>
        <div class="workspace-grid">
          <button
            v-for="ws in recents"
            :key="ws.id"
            type="button"
            class="workspace-card"
            :class="{ current: ws.id === store.workspaceId }"
            @click="openRecent(ws.id)"
          >
            <strong>{{ ws.name }}</strong>
            <span>{{ ws.root_path }}</span>
            <em class="status-pill">{{ ws.id === store.workspaceId ? '当前' : '本地' }}</em>
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: color-mix(in srgb, var(--page-bg) 28%, transparent);
  display: grid;
  place-items: center;
  padding: 24px;
}
.sheet {
  width: min(720px, 100%);
  max-height: min(80vh, 720px);
  overflow: auto;
  padding: 20px;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
header .page-panel__title { margin: 0; }
.icon-btn {
  width: 32px;
  height: 32px;
  font-size: 20px;
  line-height: 1;
}
.err {
  margin: 8px 0 0;
  color: var(--error-text);
  font-size: 12px;
}
.browse {
  margin-top: 14px;
  padding: 8px;
}
.crumbs {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
  padding: 0 6px;
  color: var(--text);
  font-size: 12px;
  font-family: var(--mono);
}
.dirs {
  list-style: none;
  margin: 0;
  padding: 0;
  min-height: 280px;
  max-height: min(52vh, 480px);
  overflow: auto;
}
.recents {
  margin-top: 20px;
}
.recents .page-panel__title { margin-bottom: 12px; }
.workspace-card.current { border-color: var(--primary); }
.workspace-card span {
  font-family: var(--mono);
  font-size: 12px;
  word-break: break-all;
}
</style>
