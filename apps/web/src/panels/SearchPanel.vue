<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import AppIcon from '@/components/AppIcon.vue'
import FileTreeIcon from '@/components/FileTreeIcon.vue'
import SearchTreeNode, { type SearchHit, type SearchTreeItem } from '@/panels/SearchTreeNode.vue'

const store = useAppStore()
const queryEl = ref<HTMLInputElement | null>(null)
const query = ref('')
const replacement = ref('')
const showReplace = ref(false)
const caseSensitive = ref(false)
const include = ref('')
const exclude = ref('')
const hits = ref<SearchHit[]>([])
const searching = ref(false)
const replacing = ref(false)
const searchError = ref('')
const viewMode = ref<'list' | 'tree'>((localStorage.getItem('ca.search.view') as 'list' | 'tree') || 'list')
const treeExpanded = ref<Set<string>>(new Set())
const activeHit = ref<{ path: string; line: number } | null>(null)
let searchTimer = 0

const searchingMode = computed(() => query.value.trim().length > 0)
const groupedHits = computed(() => {
  const map = new Map<string, SearchHit[]>()
  for (const hit of hits.value) {
    const list = map.get(hit.path) || []
    list.push(hit)
    map.set(hit.path, list)
  }
  return [...map.entries()].map(([path, items]) => ({ path, items }))
})
const hitFileCount = computed(() => groupedHits.value.length)
const treeRoots = computed(() => buildHitTree(groupedHits.value))

watch(viewMode, (mode) => {
  localStorage.setItem('ca.search.view', mode)
  if (mode === 'tree') expandAllDirs()
})

watch(groupedHits, () => {
  if (viewMode.value === 'tree') expandAllDirs()
})

function collectDirPaths(nodes: SearchTreeItem[], out: string[] = []) {
  for (const node of nodes) {
    if (node.kind === 'dir') {
      out.push(node.path)
      collectDirPaths(node.children || [], out)
    }
  }
  return out
}

function expandAllDirs() {
  treeExpanded.value = new Set(collectDirPaths(treeRoots.value))
}

function toggleTreeDir(path: string) {
  const next = new Set(treeExpanded.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  treeExpanded.value = next
}

function buildHitTree(groups: { path: string; items: SearchHit[] }[]): SearchTreeItem[] {
  const root: SearchTreeItem[] = []
  const dirs = new Map<string, SearchTreeItem>()

  function ensureDir(dirPath: string): SearchTreeItem | null {
    if (!dirPath) return null
    const existing = dirs.get(dirPath)
    if (existing) return existing
    const parentPath = dirPath.includes('/') ? dirPath.slice(0, dirPath.lastIndexOf('/')) : ''
    const node: SearchTreeItem = {
      name: dirPath.split('/').pop() || dirPath,
      path: dirPath,
      kind: 'dir',
      count: 0,
      children: [],
    }
    dirs.set(dirPath, node)
    const parent = parentPath ? ensureDir(parentPath) : null
    if (parent) parent.children!.push(node)
    else root.push(node)
    return node
  }

  for (const group of groups) {
    const parentPath = group.path.includes('/') ? group.path.slice(0, group.path.lastIndexOf('/')) : ''
    const file: SearchTreeItem = {
      name: fileName(group.path),
      path: group.path,
      kind: 'file',
      count: group.items.length,
      items: group.items,
    }
    const parent = parentPath ? ensureDir(parentPath) : null
    if (parent) parent.children!.push(file)
    else root.push(file)
  }

  function rollup(nodes: SearchTreeItem[]) {
    nodes.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    for (const node of nodes) {
      if (node.kind === 'dir') {
        rollup(node.children || [])
        node.count = (node.children || []).reduce((sum, child) => sum + child.count, 0)
      }
    }
  }
  rollup(root)
  return root
}

watch(
  [query, include, exclude, caseSensitive],
  () => {
    window.clearTimeout(searchTimer)
    searchError.value = ''
    const q = query.value.trim()
    if (!q) {
      hits.value = []
      searching.value = false
      return
    }
    searching.value = true
    searchTimer = window.setTimeout(() => {
      void runSearch(q)
    }, 280)
  },
)

watch(
  () => store.searchIntent.seq,
  async () => {
    const intent = store.searchIntent
    if (!intent.seq) return
    if (intent.clearInclude || intent.include === null) include.value = ''
    if (intent.include) include.value = intent.include
    if (intent.addExclude) {
      include.value = dropPattern(include.value, intent.addExclude)
      exclude.value = addPattern(exclude.value, intent.addExclude)
    }
    await nextTick()
    queryEl.value?.focus()
    queryEl.value?.select()
  },
  { immediate: true },
)

function addPattern(raw: string, path: string) {
  const parts = splitPatterns(raw)
  if (!parts.includes(path)) parts.push(path)
  return parts.join(', ')
}

function dropPattern(raw: string, path: string) {
  return splitPatterns(raw).filter((item) => item !== path).join(', ')
}

function splitPatterns(raw: string) {
  return raw.split(/[,;\n]+/).map((item) => item.trim().replace(/\\/g, '/').replace(/^\.\//, '')).filter(Boolean)
}

function searchParams(q: string) {
  const params = new URLSearchParams({ q })
  if (include.value.trim()) params.set('include', include.value.trim())
  if (exclude.value.trim()) params.set('exclude', exclude.value.trim())
  if (caseSensitive.value) params.set('case_sensitive', 'true')
  return params
}

async function runSearch(q: string) {
  if (!store.workspaceId) {
    searching.value = false
    return
  }
  try {
    const data = await api<{ hits: SearchHit[] }>(
      `/api/workspaces/${store.workspaceId}/search?${searchParams(q).toString()}`,
    )
    if (query.value.trim() === q) hits.value = data.hits || []
  } catch (err) {
    if (query.value.trim() === q) {
      searchError.value = err instanceof Error ? err.message : String(err)
      hits.value = []
    }
  } finally {
    if (query.value.trim() === q) searching.value = false
  }
}

function fileName(path: string) {
  return path.split('/').pop() || path
}

function snippetParts(text: string) {
  const q = query.value.trim()
  if (!q) return [{ t: text, mark: false }]
  const hay = caseSensitive.value ? text : text.toLowerCase()
  const needle = caseSensitive.value ? q : q.toLowerCase()
  const i = hay.indexOf(needle)
  if (i < 0) return [{ t: text, mark: false }]
  return [
    { t: text.slice(0, i), mark: false },
    { t: text.slice(i, i + q.length), mark: true },
    { t: text.slice(i + q.length), mark: false },
  ]
}

async function openHit(hit: SearchHit) {
  activeHit.value = { path: hit.path, line: hit.line }
  await store.openPathAtLine(hit.path, hit.line, {
    query: query.value.trim(),
    caseSensitive: caseSensitive.value,
  })
}

function clearResults() {
  query.value = ''
  hits.value = []
  searchError.value = ''
}

async function replaceAll() {
  const q = query.value.trim()
  if (!q || !store.workspaceId || replacing.value) return
  const ok = await store.askConfirm({
    title: '全部替换',
    summary: `将「${q}」替换为「${replacement.value}」。会写入磁盘，不可撤销。`,
    confirmLabel: '全部替换',
    danger: true,
  })
  if (!ok) return
  replacing.value = true
  searchError.value = ''
  try {
    const data = await api<{ files: number; replacements: number; items: { path: string; count: number }[] }>(
      `/api/workspaces/${store.workspaceId}/replace`,
      {
        method: 'POST',
        body: JSON.stringify({
          q,
          replacement: replacement.value,
          include: include.value,
          exclude: exclude.value,
          case_sensitive: caseSensitive.value,
        }),
      },
    )
    for (const item of data.items || []) await store.reloadOpenFile(item.path)
    void store.loadGitChangedPaths()
    await runSearch(q)
    if (!data.replacements) searchError.value = '没有可替换的匹配'
  } catch (err) {
    searchError.value = err instanceof Error ? err.message : String(err)
  } finally {
    replacing.value = false
  }
}

onMounted(() => queryEl.value?.focus())
onUnmounted(() => window.clearTimeout(searchTimer))
</script>

<template>
  <div class="panel-shell panel-chromeless search-panel">
    <div class="search-bar">
      <span class="title">
        <AppIcon name="search" :size="16" :stroke-width="1.75" />
        搜索
      </span>
      <span v-if="searchingMode && !searching && hits.length" class="meta">{{ hitFileCount }} 文件 · {{ hits.length }} 处</span>
      <span class="spacer" />
      <button
        type="button"
        class="icon-btn icon-btn-ghost"
        :class="{ active: viewMode === 'list' }"
        title="普通列表"
        @click="viewMode = 'list'"
      >
        <AppIcon name="list" :size="16" :stroke-width="1.75" />
      </button>
      <button
        type="button"
        class="icon-btn icon-btn-ghost"
        :class="{ active: viewMode === 'tree' }"
        title="树形展示"
        @click="viewMode = 'tree'"
      >
        <AppIcon name="tree" :size="16" :stroke-width="1.75" />
      </button>
      <button type="button" class="icon-btn icon-btn-ghost" title="刷新" :disabled="!searchingMode" @click="runSearch(query.trim())">
        <AppIcon name="refresh" :size="16" :stroke-width="1.75" />
      </button>
      <button type="button" class="icon-btn icon-btn-ghost" title="清除" @click="clearResults">
        <AppIcon name="close" :size="16" :stroke-width="1.75" />
      </button>
    </div>
    <div class="search-form">
      <div class="field">
        <AppIcon name="search" :size="16" :stroke-width="1.75" />
        <input
          ref="queryEl"
          v-model="query"
          type="text"
          placeholder="搜索文件内容"
          spellcheck="false"
          @keydown.esc="query = ''"
        />
        <button
          type="button"
          class="icon-btn icon-btn-ghost search-toggle"
          :class="{ active: caseSensitive }"
          title="区分大小写"
          @click="caseSensitive = !caseSensitive"
        >Aa</button>
        <button
          type="button"
          class="icon-btn icon-btn-ghost search-toggle"
          :class="{ active: showReplace }"
          :title="showReplace ? '收起替换' : '展开替换'"
          @click="showReplace = !showReplace"
        >
          <AppIcon name="pencil" :size="16" :stroke-width="1.75" />
        </button>
      </div>
      <div v-if="showReplace" class="replace-row">
        <div class="field">
          <AppIcon name="pencil" :size="16" :stroke-width="1.75" />
          <input
            v-model="replacement"
            type="text"
            placeholder="替换为"
            spellcheck="false"
            @keydown.enter.exact.prevent="replaceAll"
          />
        </div>
        <button
          type="button"
          class="btn"
          :disabled="!searchingMode || replacing"
          @click="replaceAll"
        >全部替换</button>
      </div>
      <label class="filter">
        <span>包含</span>
        <input v-model="include" type="text" placeholder="目录或 *.go" spellcheck="false" />
      </label>
      <label class="filter">
        <span>排除</span>
        <input v-model="exclude" type="text" placeholder="不搜索的路径" spellcheck="false" />
      </label>
    </div>
    <div class="search-results">
      <p v-if="searching" class="empty">搜索中…</p>
      <p v-else-if="searchError" class="err">{{ searchError }}</p>
      <p v-else-if="!searchingMode" class="empty">输入关键词搜索文件内容</p>
      <p v-else-if="!hits.length" class="empty">没有匹配的内容</p>
      <template v-else-if="viewMode === 'list'">
        <section v-for="group in groupedHits" :key="group.path" class="hit-group">
          <button type="button" class="hit-file" :class="{ active: activeHit?.path === group.path }" :title="group.path" @click="openHit(group.items[0])">
            <FileTreeIcon kind="file" :path="group.path" :size="16" />
            <span class="hit-name">{{ fileName(group.path) }}</span>
            <span class="hit-path">{{ group.path }}</span>
            <span class="hit-count">{{ group.items.length }}</span>
          </button>
          <button
            v-for="hit in group.items"
            :key="`${hit.path}:${hit.line}`"
            type="button"
            class="hit-line"
            :class="{ active: activeHit?.path === hit.path && activeHit?.line === hit.line }"
            @click="openHit(hit)"
          >
            <span class="hit-no">{{ hit.line }}</span>
            <span class="hit-text">
              <template v-for="(part, i) in snippetParts(hit.text)" :key="i">
                <mark v-if="part.mark">{{ part.t }}</mark>
                <template v-else>{{ part.t }}</template>
              </template>
            </span>
          </button>
        </section>
      </template>
      <div v-else class="hit-tree">
        <SearchTreeNode
          v-for="node in treeRoots"
          :key="node.path"
          :node="node"
          :depth="0"
          :expanded="treeExpanded"
          :query="query.trim()"
          :case-sensitive="caseSensitive"
          :active-path="activeHit?.path || null"
          :active-line="activeHit?.line ?? null"
          @toggle="toggleTreeDir"
          @open="openHit"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.search-panel {
  overflow: hidden;
  background: var(--sidebar-bg);
}
.search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 6px 10px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--panel-bg);
  flex-shrink: 0;
}
.title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-h);
}
.meta {
  font-size: 11px;
  color: var(--primary);
  background: var(--code-bg);
  border-radius: 999px;
  padding: 1px 7px;
}
.spacer { margin-left: auto; }
.search-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--panel-bg);
  flex-shrink: 0;
}
.field {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  height: 30px;
  padding: 0 4px 0 8px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text-muted);
}
.field:focus-within {
  border-color: var(--primary);
}
.field input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-h);
  outline: none;
  font-size: 12px;
}
.replace-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.replace-row .field { flex: 1; }
.filter {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
}
.filter span {
  flex-shrink: 0;
  width: 28px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
}
.filter input {
  flex: 1;
  min-width: 0;
  height: 28px;
  padding: 0 8px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text-h);
  outline: none;
  font-size: 12px;
  font-family: var(--mono);
}
.filter input:focus { border-color: var(--primary); }
.search-toggle {
  min-width: 22px;
  height: 22px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.search-results {
  flex: 1;
  overflow: auto;
  padding: 6px 0 12px;
}
.empty {
  margin: 24px 12px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}
.err {
  margin: 0;
  padding: 8px 12px;
  color: var(--danger);
  font-size: 12px;
}
.hit-group { padding: 2px 0 6px; }
.hit-file,
.hit-line {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.hit-file {
  padding: 6px 12px;
  color: var(--text-h);
}
.hit-file:hover,
.hit-line:hover { background: var(--bg-muted); }
.hit-file.active,
.hit-line.active { background: var(--primary-soft); }
.hit-name {
  font-size: 12.5px;
  font-weight: 600;
  flex-shrink: 0;
}
.hit-path {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  font-family: var(--mono);
  color: var(--text-muted);
}
.hit-count {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-muted);
}
.hit-line {
  padding: 4px 12px 4px 36px;
  color: var(--text);
  font-size: 12.5px;
}
.hit-no {
  flex-shrink: 0;
  width: 28px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-muted);
  text-align: right;
}
.hit-text {
  min-width: 0;
  font-family: var(--mono);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hit-text mark {
  padding: 0 1px;
  border-radius: 2px;
  background: var(--primary-soft);
  color: var(--text-h);
  font-weight: 600;
}
</style>

