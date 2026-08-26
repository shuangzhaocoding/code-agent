<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { useWorkspaceBrowse } from '@/composables/useWorkspaceBrowse'
import AppIcon from '@/components/AppIcon.vue'
import WorkspaceMkdirRow from '@/components/WorkspaceMkdirRow.vue'

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
  } catch (err) {
    error.value = errMessage(err)
  }
}

async function openRecent(id: string) {
  error.value = ''
  try {
    await store.selectWorkspace(id)
  } catch (err) {
    error.value = errMessage(err)
  }
}

const recents = computed(() => store.workspaces)
</script>

<template>
  <div class="panel-shell workspace-panel">
    <header class="panel-head">
      <span class="panel-title">打开工作空间</span>
    </header>
    <div class="workspace-body">
      <p class="lead">选择本地目录，或从最近工作空间进入。</p>
      <div class="search-box compact">
        <AppIcon class="search-box-icon" name="folder" :size="16" />
        <input v-model="path" placeholder="/path/to/project" @keydown.enter="openPath" />
        <button type="button" class="search-box-btn" @click="openPath">打开</button>
      </div>
      <p v-if="error" class="err">{{ error }}</p>

      <div class="nested-list browse">
        <div class="crumbs">
          <button type="button" class="btn btn-ghost mini" @click="browse(browsing?.parent || '~')">上级</button>
          <button type="button" class="btn btn-ghost mini" @click="startCreate">新建文件夹</button>
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
              <AppIcon name="folder" :size="14" />
              {{ item.name }}
            </button>
          </li>
        </ul>
      </div>

      <section v-if="recents.length" class="recents">
        <h2 class="section-title">最近打开</h2>
        <div class="recent-list">
          <button
            v-for="ws in recents"
            :key="ws.id"
            type="button"
            class="recent-card"
            :class="{ current: ws.id === store.workspaceId }"
            @click="openRecent(ws.id)"
          >
            <strong>{{ ws.name }}</strong>
            <span>{{ ws.root_path }}</span>
            <em v-if="ws.id === store.workspaceId" class="status-pill">当前</em>
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.workspace-panel {
  background: var(--panel-bg);
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
}

.workspace-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

.lead {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
}

.search-box.compact {
  padding: 4px 4px 4px 10px;
  border-radius: var(--radius-sm);
}

.search-box.compact input {
  height: 32px;
  font-size: 12px;
}

.search-box.compact .search-box-btn {
  height: 32px;
  min-width: 56px;
  padding: 0 12px;
  font-size: 12px;
}

.err {
  margin: 8px 0 0;
  color: var(--error-text);
  font-size: 12px;
}

.browse {
  margin-top: 10px;
  padding: 6px;
}

.crumbs {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
  padding: 0 4px;
  color: var(--text);
  font-size: 11px;
  font-family: var(--mono);
}

.crumbs span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.btn.mini {
  height: 24px;
  padding: 0 8px;
  font-size: 11px;
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
  margin-top: 14px;
}

.section-title {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recent-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--page-bg);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.recent-card:hover {
  border-color: var(--primary);
}

.recent-card.current {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.recent-card strong {
  font-size: 13px;
  color: var(--text-h);
}

.recent-card span {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-secondary);
  word-break: break-all;
}

.recent-card .status-pill {
  align-self: flex-start;
}
</style>
