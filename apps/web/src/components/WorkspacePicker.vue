<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import { currentTheme, toggleTheme, type Theme } from '@/theme'
import AppIcon from '@/components/AppIcon.vue'
import AuthScene from '@/components/AuthScene.vue'

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
  <div class="auth-page">
    <AuthScene />
    <div class="auth-locale">
      <button type="button" class="icon-btn" title="切换主题" @click="onToggleTheme">
        <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
      </button>
    </div>
    <div class="auth-card">
      <div class="auth-brand">Code Agent</div>
      <h1>对着真实仓库工作的开源编码 Agent</h1>
      <p class="auth-lead">无登录 · 可插拔 Skill / 模型 · 刷新后续流 · 窗口可拖动排版</p>

      <div class="search-box">
        <AppIcon class="search-box-icon" name="folder" :size="20" />
        <input v-model="path" placeholder="/path/to/project" @keydown.enter="open" />
        <button type="button" class="search-box-btn" @click="open">打开</button>
      </div>

      <div class="browse">
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

      <section v-if="recents.length" class="recents">
        <h2>最近打开</h2>
        <button
          v-for="ws in recents"
          :key="ws.id"
          type="button"
          class="recent"
          @click="store.selectWorkspace(ws.id)"
        >
          <strong>{{ ws.name }}</strong>
          <span>{{ ws.root_path }}</span>
        </button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.browse {
  margin-top: 18px;
}
.crumbs {
  display: flex;
  gap: 12px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 12px;
  font-family: var(--mono);
  margin-bottom: 8px;
}
.dirs {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 220px;
  overflow: auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
}
.recents {
  margin-top: 20px;
  border-top: 1px solid var(--border);
  padding-top: 16px;
}
.recents h2 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 600;
}
.recent {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 10px 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}
.recent:hover { background: var(--primary-soft); }
.recent span {
  color: var(--text-muted);
  font-size: 12px;
  font-family: var(--mono);
}
@media (max-width: 720px) {
  .dirs { grid-template-columns: 1fr; }
}
</style>
