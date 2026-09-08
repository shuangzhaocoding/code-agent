<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { useWorkspaceBrowse } from '@/composables/useWorkspaceBrowse'
import AppIcon from '@/components/AppIcon.vue'
import WorkspaceMkdirRow from '@/components/WorkspaceMkdirRow.vue'

const emit = defineEmits<{ close: [] }>()
const store = useAppStore()
const { path, error, creating, createValue, createKey, dirs, displayPath, canGoParent, atRoots, browse, goParent, startCreate, cancelCreate, commitCreate, errMessage } = useWorkspaceBrowse()

onMounted(async () => {
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
</script>

<template>
  <Teleport to="body">
    <div class="mask" @click.self="emit('close')">
      <div class="page-panel sheet" role="dialog" aria-label="打开工作区">
        <header>
          <h1 class="page-panel__title">打开工作空间</h1>
          <button type="button" class="ghost-icon-btn" title="关闭" @click="emit('close')">
            <AppIcon name="close" :size="16" :stroke-width="1.75" />
          </button>
        </header>
        <p class="page-panel__lead">选择本地目录作为工作空间。</p>
        <div class="search-box compact">
          <AppIcon class="search-box-icon" name="folder" :size="14" :stroke-width="1.75" />
          <input v-model="path" placeholder="/path/to/project" @keydown.enter="openPath" />
          <button type="button" class="search-box-btn" @click="openPath">打开</button>
        </div>
        <p v-if="error" class="err">{{ error }}</p>
        <div class="nested-list browse">
          <div class="crumbs">
            <button type="button" class="btn btn-ghost" :disabled="!canGoParent" @click="goParent">上级</button>
            <button type="button" class="btn btn-ghost" :disabled="atRoots" @click="startCreate">新建文件夹</button>
            <span>{{ displayPath }}</span>
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
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: color-mix(in srgb, var(--page-bg) 28%, transparent);
  display: grid;
  place-items: center;
  padding: 16px;
}
.sheet {
  width: min(560px, 100%);
  max-height: min(72vh, 560px);
  overflow: auto;
  padding: 14px 16px 16px;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
header .page-panel__title {
  margin: 0;
  font-size: 14px;
}
.page-panel__lead {
  margin: 8px 0 10px;
  font-size: 12px;
}
.search-box.compact {
  gap: 6px;
  padding: 3px 3px 3px 10px;
  border-radius: var(--radius-sm);
}
.search-box.compact :deep(input) {
  height: 28px;
  font-size: 12px;
}
.search-box.compact :deep(.search-box-btn) {
  height: 28px;
  min-width: 52px;
  padding: 0 12px;
  font-size: 12px;
  border-radius: var(--radius-sm);
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
.dirs {
  list-style: none;
  margin: 0;
  padding: 0;
  min-height: 220px;
  max-height: min(48vh, 360px);
  overflow: auto;
}
</style>
