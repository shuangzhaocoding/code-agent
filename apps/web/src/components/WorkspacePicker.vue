<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import { currentTheme, toggleTheme, type Theme } from '@/theme'
import AppIcon from '@/components/AppIcon.vue'
import BrandMark from '@/components/BrandMark.vue'

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
        <BrandMark :size="26" />
        <span class="brand-name">Code Agent</span>
      </div>
      <div class="layout-actions">
        <button type="button" class="icon-btn icon-btn-ghost" title="切换主题" @click="onToggleTheme">
          <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
        </button>
      </div>
    </header>

    <main class="launch-main">
      <section class="launch-hero">
        <BrandMark :size="48" class="hero-logo" />
        <h1>打开工作空间</h1>
        <p>本地优先 · 无登录 · 刷新后续流</p>
        <div class="search-box">
          <AppIcon class="search-box-icon" name="folder" :size="18" />
          <input v-model="path" placeholder="输入项目路径…" @keydown.enter="open" />
          <button type="button" class="search-box-btn" @click="open">打开</button>
        </div>
      </section>

      <section v-if="recents.length" class="recents">
        <h2>最近打开</h2>
        <div class="recents-scroll">
          <button
            v-for="ws in recents"
            :key="ws.id"
            type="button"
            class="workspace-card"
            @click="store.selectWorkspace(ws.id)"
          >
            <strong>{{ ws.name }}</strong>
            <span>{{ ws.root_path }}</span>
          </button>
        </div>
      </section>

      <section class="browse-section">
        <div class="browse-head">
          <span class="browse-label">浏览目录</span>
          <button type="button" class="browse-up" @click="browse(browsing?.parent || '~')">上级</button>
        </div>
        <p class="browse-path">{{ browsing?.path }}</p>
        <ul class="dirs">
          <li v-for="item in dirs" :key="item.path">
            <button type="button" class="dir-item" @click="browse(item.path)">
              <AppIcon name="folder" :size="15" />
              {{ item.name }}
            </button>
          </li>
        </ul>
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
  gap: 32px;
  padding: 32px 20px 56px;
  max-width: 720px;
  margin: 0 auto;
  width: 100%;
}
.launch-hero {
  width: 100%;
  text-align: center;
}
.hero-logo {
  margin: 0 auto 16px;
}
.launch-hero h1 {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text-h);
}
.launch-hero p {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--text-secondary);
}
.launch-hero .search-box {
  max-width: 480px;
  margin: 0 auto;
  padding: 5px 5px 5px 12px;
  border-radius: var(--radius-md);
  background: var(--panel-bg);
}
.launch-hero .search-box input {
  height: 38px;
  font-size: 14px;
}
.launch-hero .search-box-btn {
  height: 38px;
  min-width: 72px;
  padding: 0 16px;
  font-size: 13px;
  border-radius: var(--radius-sm);
}
.recents {
  width: 100%;
}
.recents h2 {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}
.recents-scroll {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
}
.workspace-card {
  flex: 0 0 220px;
  min-height: 88px;
  padding: 14px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  color: inherit;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.workspace-card:hover {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  background: color-mix(in srgb, var(--primary-soft) 50%, var(--panel-bg));
}
.workspace-card strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-h);
}
.workspace-card span {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-muted);
  word-break: break-all;
  line-height: 1.4;
}
.browse-section {
  width: 100%;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  overflow: hidden;
}
.browse-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: var(--border-width) solid var(--border);
}
.browse-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
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
  max-height: 240px;
  overflow: auto;
}
.dir-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}
.dir-item:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
</style>
