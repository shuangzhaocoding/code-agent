<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { currentTheme, toggleTheme, type Theme } from '@/theme'
import { useWorkspaceBrowse } from '@/composables/useWorkspaceBrowse'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import LanguageSelect from '@/components/LanguageSelect.vue'
import BrandMark from '@/components/BrandMark.vue'
import WorkspaceMkdirRow from '@/components/WorkspaceMkdirRow.vue'

const { t } = useI18n()
const store = useAppStore()
const theme = ref<Theme>(currentTheme())
const { browsing, path, error, creating, createValue, createKey, dirs, browse, startCreate, cancelCreate, commitCreate, errMessage } = useWorkspaceBrowse('~')

onMounted(async () => {
  await store.loadWorkspaces()
  await browse('~')
})

async function open() {
  if (!path.value) return
  error.value = ''
  try {
    await store.addWorkspace(path.value)
  } catch (err) {
    error.value = errMessage(err)
  }
}

function onToggleTheme() {
  theme.value = toggleTheme()
}

const recents = computed(() => store.workspaces)
</script>

<template>
  <div class="launch-page">
    <header class="launch-header">
      <div class="launch-brand">
        <BrandMark :size="24" />
        <span>Code Agent</span>
      </div>
      <div class="launch-actions">
        <LanguageSelect />
        <button type="button" class="launch-theme" :title="t('theme.toggle')" @click="onToggleTheme">
          <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
        </button>
      </div>
    </header>

    <main class="launch-body">
      <div class="launch-path">
        <AppIcon name="folder" :size="15" />
        <input v-model="path" :placeholder="t('workspace.pathPlaceholder')" @keydown.enter="open" />
        <button type="button" class="btn btn-primary" @click="open">{{ t('common.open') }}</button>
      </div>
      <p v-if="error" class="launch-err">{{ error }}</p>

      <div class="launch-split">
        <section class="launch-col">
          <h2>{{ t('workspace.recent') }}</h2>
          <p v-if="!recents.length" class="launch-empty">{{ t('workspace.emptyRecent') }}</p>
          <button
            v-for="ws in recents"
            :key="ws.id"
            type="button"
            class="recent-item"
            :title="ws.root_path"
            @click="store.selectWorkspace(ws.id)"
          >
            <AppIcon name="folder" :size="15" />
            <span class="recent-copy">
              <strong>{{ ws.name }}</strong>
              <span>{{ ws.root_path }}</span>
            </span>
          </button>
        </section>

        <section class="launch-col">
          <div class="browse-head">
            <h2>{{ t('workspace.browse') }}</h2>
            <div class="browse-actions">
              <button type="button" class="browse-up" @click="startCreate">{{ t('workspace.newFolder') }}</button>
              <button type="button" class="browse-up" @click="browse(browsing?.parent || '~')">{{ t('common.parent') }}</button>
            </div>
          </div>
          <p class="browse-path" :title="browsing?.path">{{ browsing?.path }}</p>
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
              <button type="button" class="dir-item" @click="browse(item.path)">
                <AppIcon name="folder" :size="15" />
                {{ item.name }}
              </button>
            </li>
          </ul>
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
.launch-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--page-bg);
}
.launch-header {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px 0 12px;
  background: var(--sidebar-bg);
  border-bottom: var(--border-width) solid var(--border);
  flex-shrink: 0;
}
.launch-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 14px;
  color: var(--text-h);
  letter-spacing: -0.02em;
}
.launch-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.launch-theme {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.launch-theme:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.launch-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
}
.launch-path {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 6px 0 10px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text-muted);
}
.launch-path input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-h);
  outline: none;
  font-size: 13px;
  font-family: var(--mono);
}
.launch-path .btn {
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
}
.launch-err {
  margin: 0;
  color: var(--error-text);
  font-size: 12px;
}
.browse-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.launch-split {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 12px;
}
.launch-col {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  overflow: auto;
}
.launch-col h2,
.browse-head h2 {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.launch-col > h2 {
  padding: 10px 12px;
  border-bottom: var(--border-width) solid var(--border);
}
.launch-empty {
  margin: 0;
  padding: 24px 12px;
  font-size: 13px;
  color: var(--text-muted);
}
.recent-item,
.dir-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: 0;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.recent-item:hover,
.dir-item:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.recent-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.recent-copy strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
}
.recent-copy span {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.browse-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: var(--border-width) solid var(--border);
}
.browse-up {
  border: 0;
  background: transparent;
  color: var(--primary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}
.browse-up:hover {
  background: var(--code-bg);
}
.browse-path {
  margin: 0;
  padding: 8px 12px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-muted);
  border-bottom: var(--border-width) solid var(--border);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dirs {
  list-style: none;
  margin: 0;
  padding: 4px;
  overflow: auto;
  flex: 1;
}
@media (max-width: 720px) {
  .launch-split {
    grid-template-columns: 1fr;
  }
}
</style>
