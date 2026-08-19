<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import { currentTheme, toggleTheme, type Theme } from '@/theme'
import AppIcon from '@/components/AppIcon.vue'

const store = useAppStore()
const path = ref('')
const theme = ref<Theme>(currentTheme())
const browsing = ref<{ path: string; parent: string; items: { name: string; path: string; is_dir: boolean }[] } | null>(null)

onMounted(async () => {
  await store.loadWorkspaces()
  await browse('~')
})

async function browse(p: string) {
  browsing.value = await api(`/api/workspaces/browse?path=${encodeURIComponent(p)}`)
  path.value = browsing.value?.path || p
}

async function open() {
  if (!path.value) return
  await store.addWorkspace(path.value)
}

function onToggleTheme() {
  theme.value = toggleTheme()
}

const recents = computed(() => store.workspaces)
const dirs = computed(() => browsing.value?.items.filter((i) => i.is_dir) || [])
</script>

<template>
  <div class="launch-page">
    <header class="layout-header">
      <div class="layout-brand">
        <span class="brand-mark">CA</span>
        <span>Code Agent</span>
      </div>
      <div class="layout-actions">
        <button type="button" class="icon-btn" title="切换主题" @click="onToggleTheme">
          <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
        </button>
      </div>
    </header>

    <main class="launch-main">
      <section class="launch__panel">
        <h1>打开工作空间</h1>
        <p>无登录 · 可插拔 Skill / 模型 · 刷新后续流。选择一个本地目录开始。</p>
        <div class="search-box">
          <AppIcon class="search-box-icon" name="folder" :size="20" />
          <input v-model="path" placeholder="/path/to/project" @keydown.enter="open" />
          <button type="button" class="search-box-btn" @click="open">打开</button>
        </div>
        <div class="browse nested-list">
          <div class="crumbs">
            <button type="button" class="btn btn-ghost" @click="browse(browsing?.parent || '~')">上级</button>
            <span>{{ browsing?.path }}</span>
          </div>
          <ul class="dirs">
            <li v-for="item in dirs" :key="item.path">
              <button type="button" class="menu-item" @click="browse(item.path)">
                <AppIcon name="folder" :size="15" />
                {{ item.name }}
              </button>
            </li>
          </ul>
        </div>
      </section>

      <section v-if="recents.length" class="recents">
        <h2 class="page-panel__title">最近打开</h2>
        <p class="page-panel__lead">点击卡片进入已有工作空间。</p>
        <div class="workspace-grid">
          <button
            v-for="ws in recents"
            :key="ws.id"
            type="button"
            class="workspace-card"
            @click="store.selectWorkspace(ws.id)"
          >
            <strong>{{ ws.name }}</strong>
            <span>{{ ws.root_path }}</span>
            <em class="status-pill">本地</em>
          </button>
        </div>
      </section>
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
.launch-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 28px;
  padding: 32px 20px 48px;
}
.launch__panel {
  width: min(420px, 100%);
}
.launch__panel .search-box {
  padding: 6px 6px 6px 14px;
  border-radius: var(--radius-md);
}
.launch__panel .search-box input { height: 36px; font-size: 14px; }
.launch__panel .search-box-btn {
  height: 36px;
  min-width: 72px;
  padding: 0 16px;
  font-size: 13px;
}
.browse {
  margin-top: 16px;
  padding: 8px;
}
.crumbs {
  display: flex;
  gap: 12px;
  align-items: center;
  color: var(--text);
  font-size: 12px;
  font-family: var(--mono);
  margin-bottom: 8px;
  padding: 0 6px;
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
  max-height: 220px;
  overflow: auto;
}
.recents {
  width: min(960px, 100%);
}
.workspace-card span {
  font-family: var(--mono);
  font-size: 12px;
  word-break: break-all;
}
</style>
