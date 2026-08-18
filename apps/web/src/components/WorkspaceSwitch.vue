<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import AppIcon from '@/components/AppIcon.vue'

const emit = defineEmits<{ close: [] }>()
const store = useAppStore()
const path = ref(store.workspace?.root_path || '')
const error = ref('')
const browsing = ref<{ path: string; parent: string; items: { name: string; path: string; is_dir: boolean }[] } | null>(null)

onMounted(async () => {
  await store.loadWorkspaces()
  await browse(path.value || '~')
})

async function browse(p: string) {
  browsing.value = await api(`/api/workspaces/browse?path=${encodeURIComponent(p)}`)
  path.value = browsing.value?.path || p
}

async function openPath() {
  if (!path.value) return
  error.value = ''
  try {
    await store.addWorkspace(path.value)
    emit('close')
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

async function openRecent(id: string) {
  await store.selectWorkspace(id)
  emit('close')
}

const recents = computed(() => store.workspaces)
const dirs = computed(() => browsing.value?.items.filter((i) => i.is_dir) || [])
</script>

<template>
  <div class="mask" @click.self="emit('close')">
    <div class="sheet" role="dialog" aria-label="打开工作区">
      <header>
        <strong>打开工作区</strong>
        <button type="button" class="icon-btn" title="关闭" @click="emit('close')">×</button>
      </header>
      <div class="search-box">
        <AppIcon class="search-box-icon" name="folder" :size="18" />
        <input v-model="path" placeholder="/path/to/project" @keydown.enter="openPath" />
        <button type="button" class="search-box-btn" @click="openPath">打开</button>
      </div>
      <p v-if="error" class="err">{{ error }}</p>
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
      <section v-if="recents.length" class="recents">
        <h2>最近打开</h2>
        <button
          v-for="ws in recents"
          :key="ws.id"
          type="button"
          class="recent"
          :class="{ current: ws.id === store.workspaceId }"
          @click="openRecent(ws.id)"
        >
          <strong>{{ ws.name }}</strong>
          <span>{{ ws.root_path }}</span>
        </button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: rgba(15, 23, 42, 0.42);
  display: grid;
  place-items: center;
  padding: 24px;
}
.sheet {
  width: min(640px, 100%);
  max-height: min(80vh, 720px);
  overflow: auto;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 18px 20px 20px;
  box-shadow: var(--shadow-md);
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
header strong { font-size: 16px; }
.icon-btn {
  width: 32px;
  height: 32px;
  font-size: 20px;
  line-height: 1;
}
.err {
  margin: 8px 0 0;
  color: var(--danger);
  font-size: 12px;
}
.crumbs {
  display: flex;
  gap: 10px;
  align-items: center;
  margin: 14px 0 8px;
  color: var(--text-secondary);
  font-size: 12px;
  font-family: var(--mono);
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
  margin-top: 16px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}
.recents h2 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-secondary);
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
.recent:hover,
.recent.current { background: var(--primary-soft); }
.recent span {
  color: var(--text-muted);
  font-size: 12px;
  font-family: var(--mono);
}
</style>
