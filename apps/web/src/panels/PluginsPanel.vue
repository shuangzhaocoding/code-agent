<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'

type PluginTool = { name: string; description: string; enabled: boolean }
type PluginProvider = { kind: string; title: string; enabled: boolean }
type PluginPreset = { kind: string; name: string; title: string; base_url: string }

type PluginItem = {
  id: string
  title: string
  description: string
  source: string
  enabled: boolean
  kind: string
  version: string
  api: number
  origin: string
  contributes: string[]
  error?: string | null
  author?: string | null
  homepage?: string | null
  repository?: string | null
  license?: string | null
  icon?: string | null
  icon_url?: string | null
  accent?: string | null
  keywords?: string[]
  providers: PluginProvider[]
  tools: PluginTool[]
  presets: PluginPreset[]
}

const loading = ref(false)
const query = ref('')
const filter = ref('all')
const items = ref<PluginItem[]>([])
const expanded = ref<string | null>(null)
const copied = ref<string | null>(null)
const error = ref('')
const store = useAppStore()

const ORIGIN: Record<string, { label: string; accent: string }> = {
  builtin: { label: '内置', accent: '#4f6bff' },
  repo: { label: '仓库', accent: '#0891b2' },
  user: { label: '用户', accent: '#059669' },
  workspace: { label: '工作区', accent: '#d97706' },
  python: { label: 'Python', accent: '#64748b' },
}

const KIND_LABEL: Record<string, string> = {
  'llm.provider': '模型适配',
  tools: '工具',
  python: '工具',
}

const filters = [
  { id: 'all', label: '全部' },
  { id: 'llm.provider', label: '模型适配' },
  { id: 'tools', label: '工具' },
  { id: 'builtin', label: '内置' },
]

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return items.value.filter((p) => {
    if (filter.value === 'llm.provider' && !p.contributes.includes('llm.provider') && p.kind !== 'llm.provider') {
      return false
    }
    if (filter.value === 'tools' && !p.contributes.includes('tools') && p.kind !== 'tools' && p.kind !== 'python') {
      return false
    }
    if (filter.value === 'builtin' && p.origin !== 'builtin') return false
    if (!q) return true
    const haystack = [
      p.title,
      p.description,
      p.id,
      p.source,
      p.kind,
      p.author,
      p.license,
      p.homepage,
      p.repository,
      ...(p.keywords || []),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(q)
  })
})

const stats = computed(() => ({
  total: items.value.length,
  llm: items.value.filter((p) => p.contributes.includes('llm.provider') || p.kind === 'llm.provider').length,
  off: items.value.filter((p) => p.error || !p.enabled).length,
}))

function originMeta(origin: string) {
  return ORIGIN[origin] || { label: origin || '插件', accent: '#64748b' }
}

function pluginIcon(plugin: PluginItem) {
  if (plugin.icon_url) return null
  if (plugin.icon) return plugin.icon
  return plugin.contributes.includes('llm.provider') ? 'chip' : 'puzzle'
}

function pluginAccent(plugin: PluginItem) {
  return plugin.accent || originMeta(plugin.origin).accent
}

function externalUrl(url?: string | null) {
  if (!url) return null
  return /^https?:\/\//i.test(url) ? url : `https://${url}`
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const data = await api<{ plugins: PluginItem[] }>('/api/plugins')
    items.value = data.plugins || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function toggleEnabled(plugin: PluginItem) {
  try {
    await api(`/api/plugins/${encodeURIComponent(plugin.id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled: !plugin.enabled }),
    })
    await refresh()
    if (plugin.contributes.includes('llm.provider') || plugin.kind === 'llm.provider') {
      await store.loadProviders()
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

async function copyPath(path: string) {
  try {
    await navigator.clipboard.writeText(path)
    copied.value = path
    setTimeout(() => {
      if (copied.value === path) copied.value = null
    }, 1500)
  } catch {
    /* ignore */
  }
}

onMounted(() => {
  void refresh()
})
</script>

<template>
  <div class="panel-shell plugins-panel">
    <div class="panel-body">
      <header class="page-head">
        <div>
          <h1 class="page-title">插件</h1>
          <p class="page-lead">已安装并完成注册的扩展。模型适配器决定如何拉模型、探测连通性和发起对话请求。</p>
        </div>
        <button type="button" class="btn btn-ghost" :disabled="loading" @click="refresh">
          <AppIcon name="refresh" :size="16" :stroke-width="1.75" />
          刷新
        </button>
      </header>

      <section class="tip-card">
        <span class="tip-icon"><AppIcon name="puzzle" :size="16" /></span>
        <div class="tip-copy">
          <strong>安装位置</strong>
          <p>
            仓库 <code>plugins/</code>
            · 用户 <code>~/.code-agent/plugins/</code>
            · 工作区 <code>.code-agent/plugins/</code>
          </p>
          <p>模型适配器实现 <code>LlmAdapter</code>，在 <code>register(registry)</code> 里调用 <code>register_llm_adapter</code>。</p>
        </div>
      </section>

      <p v-if="error" class="error">{{ error }}</p>

      <div class="toolbar">
        <div class="search">
          <AppIcon name="search" :size="16" :stroke-width="1.75" />
          <input v-model="query" type="search" placeholder="搜索名称、来源或类型" />
        </div>
        <div class="filters">
          <button
            v-for="item in filters"
            :key="item.id"
            type="button"
            class="chip"
            :class="{ on: filter === item.id }"
            @click="filter = item.id"
          >
            {{ item.label }}
          </button>
        </div>
        <div class="stats">
          <span>{{ stats.total }} 已安装</span>
          <span>{{ stats.llm }} 个模型适配</span>
          <span v-if="stats.off" class="bad">{{ stats.off }} 停用/异常</span>
        </div>
      </div>

      <div v-if="!filtered.length" class="empty">
        <AppIcon name="puzzle" :size="28" />
        <p>{{ items.length ? '没有匹配的插件' : '还没有发现插件' }}</p>
        <small>将 Python 文件放到 plugins/ 后点刷新。</small>
      </div>

      <div v-else class="plugin-grid">
        <article
          v-for="p in filtered"
          :key="p.id"
          class="plugin-card"
          :class="{ open: expanded === p.id, off: !p.enabled, invalid: !!p.error }"
        >
          <button type="button" class="plugin-main" @click="expanded = expanded === p.id ? null : p.id">
            <span class="plugin-icon" :style="{ '--accent': pluginAccent(p) }">
              <img v-if="p.icon_url" :src="p.icon_url" alt="" class="plugin-icon-img" />
              <AppIcon v-else :name="pluginIcon(p) || 'puzzle'" :size="18" />
            </span>
            <span class="plugin-copy">
              <span class="plugin-title-row">
                <strong>{{ p.title }}</strong>
                <span class="source-pill" :style="{ '--accent': originMeta(p.origin).accent }">
                  {{ originMeta(p.origin).label }}
                </span>
                <span class="source-pill kind">{{ KIND_LABEL[p.kind] || p.kind }}</span>
              </span>
              <span class="plugin-desc">{{ p.description || '暂无描述' }}</span>
            </span>
            <AppIcon class="chevron" name="chevron-right" :size="16" />
          </button>

          <div class="plugin-meta">
            <span v-if="p.error" class="status bad">{{ p.error }}</span>
            <span v-else-if="p.enabled" class="status ok">已启用</span>
            <span v-else class="status off">已停用</span>
            <button type="button" class="toggle-btn" @click.stop="toggleEnabled(p)">
              {{ p.enabled ? '停用' : '启用' }}
            </button>
          </div>

          <div v-if="expanded === p.id" class="plugin-detail">
            <button type="button" class="path-btn" :title="p.source" @click.stop="copyPath(p.source)">
              <AppIcon name="file" :size="12" />
              <span>{{ p.source }}</span>
              <em>{{ copied === p.source ? '已复制' : '复制路径' }}</em>
            </button>
            <div class="detail-tags">
              <span class="tag">id · {{ p.id }}</span>
              <span class="tag">v{{ p.version || '1.0.0' }}</span>
              <span class="tag">api {{ p.api || 1 }}</span>
              <span v-if="p.author" class="tag">作者 · {{ p.author }}</span>
              <span v-if="p.license" class="tag">许可 · {{ p.license }}</span>
              <span v-for="c in p.contributes" :key="c" class="tag">{{ c }}</span>
              <span v-for="kw in p.keywords || []" :key="kw" class="tag keyword">{{ kw }}</span>
            </div>
            <div v-if="p.homepage || p.repository" class="detail-block links-block">
              <h3>链接</h3>
              <ul class="link-list">
                <li v-if="p.homepage">
                  <AppIcon name="globe" :size="16" :stroke-width="1.75" />
                  <a :href="externalUrl(p.homepage) || '#'" target="_blank" rel="noopener noreferrer">主页</a>
                  <span>{{ p.homepage }}</span>
                </li>
                <li v-if="p.repository">
                  <AppIcon name="git" :size="16" :stroke-width="1.75" />
                  <a :href="externalUrl(p.repository) || '#'" target="_blank" rel="noopener noreferrer">源码</a>
                  <span>{{ p.repository }}</span>
                </li>
              </ul>
            </div>
            <div v-if="p.providers.length" class="detail-block">
              <h3>注册的模型适配</h3>
              <ul>
                <li v-for="prov in p.providers" :key="prov.kind">
                  <code>{{ prov.kind }}</code>
                  <span>{{ prov.title }}</span>
                </li>
              </ul>
            </div>
            <div v-if="p.presets.length" class="detail-block">
              <h3>预设</h3>
              <ul>
                <li v-for="preset in p.presets" :key="preset.kind">
                  <code>{{ preset.kind }}</code>
                  <span>{{ preset.title || preset.name }} · {{ preset.base_url }}</span>
                </li>
              </ul>
            </div>
            <div v-if="p.tools.length" class="detail-block">
              <h3>注册的工具</h3>
              <ul>
                <li v-for="tool in p.tools" :key="tool.name">
                  <code>{{ tool.name }}</code>
                  <span>{{ tool.description || '无描述' }}</span>
                </li>
              </ul>
            </div>
          </div>
        </article>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plugins-panel .panel-body {
  padding: 18px 20px 28px;
  overflow: auto;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  color: var(--text-h);
}
.page-lead {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.tip-card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 14px;
  margin-bottom: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--primary) 6%, var(--panel-bg));
}
.tip-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  color: var(--primary);
  background: var(--primary-soft);
  flex-shrink: 0;
}
.tip-copy strong {
  display: block;
  font-size: 12.5px;
  color: var(--text-h);
}
.tip-copy p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.55;
}
.tip-copy code {
  font-family: var(--mono);
  font-size: 11.5px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--bg);
  border: 1px solid var(--border);
}
.error {
  margin: 0 0 12px;
  color: #dc2626;
  font-size: 13px;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 16px;
}
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: min(260px, 100%);
  flex: 1;
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text-secondary);
}
.search input {
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-h);
  font-size: 13px;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  border-radius: var(--ghost-btn-radius);
  padding: 0 8px;
  height: var(--ghost-btn-height);
  font-size: var(--ghost-btn-font-size);
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s ease, color 0.12s ease;
}
.chip:hover:not(.on) {
  opacity: var(--ghost-hover-opacity);
  color: var(--text-h);
}
.chip.on {
  color: var(--primary);
  opacity: 1;
}
.stats {
  display: flex;
  gap: 10px;
  margin-left: auto;
  font-size: 12px;
  color: var(--text-h);
}
.stats .bad {
  color: #dc2626;
}
.empty {
  display: grid;
  place-items: center;
  gap: 6px;
  padding: 48px 16px;
  color: var(--text-secondary);
  text-align: center;
}
.empty p {
  margin: 0;
  font-size: 14px;
  color: var(--text-h);
}
.plugin-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.plugin-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  overflow: hidden;
}
.plugin-card.open {
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
}
.plugin-card.off {
  opacity: 0.8;
}
.plugin-main {
  display: grid;
  grid-template-columns: 40px 1fr 16px;
  gap: 10px;
  width: 100%;
  padding: 14px 14px 8px;
  border: 0;
  background: transparent;
  text-align: left;
  color: inherit;
  cursor: pointer;
}
.plugin-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  overflow: hidden;
}
.plugin-icon-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.plugin-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.plugin-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.plugin-title-row strong {
  font-size: 14px;
  color: var(--text-h);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-pill {
  flex-shrink: 0;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  color: var(--accent, #4f6bff);
  background: color-mix(in srgb, var(--accent, #4f6bff) 12%, transparent);
}
.source-pill.kind {
  color: #64748b;
  background: color-mix(in srgb, #64748b 12%, transparent);
}
.plugin-desc {
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.plugin-author {
  font-size: 11.5px;
  color: var(--text-secondary);
}
.source-pill.version {
  color: #64748b;
  background: color-mix(in srgb, #64748b 10%, transparent);
}
.chevron {
  margin-top: 10px;
  color: var(--text-secondary);
}
.plugin-card.open .chevron {
  transform: rotate(90deg);
}
.plugin-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 0 14px 12px;
}
.path-btn {
  flex: 1;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid transparent;
  background: var(--bg);
  border-radius: 8px;
  padding: 5px 8px;
  color: var(--text-secondary);
  cursor: pointer;
}
.path-btn span {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--mono);
  font-size: 11px;
}
.path-btn em {
  font-style: normal;
  font-size: 11px;
}
.status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
}
.status.ok {
  color: #059669;
  background: color-mix(in srgb, #10b981 12%, transparent);
}
.status.off,
.status.bad {
  color: #dc2626;
  background: color-mix(in srgb, #ef4444 12%, transparent);
}
.toggle-btn {
  height: var(--ghost-btn-height);
  padding: 0 8px;
  border: 0;
  border-radius: var(--ghost-btn-radius);
  background: transparent;
  color: var(--text-h);
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
  transition: opacity 0.15s ease;
}
.toggle-btn:hover {
  background: transparent;
  color: var(--text-h);
  opacity: var(--ghost-hover-opacity);
}
.plugin-detail {
  border-top: 1px solid var(--border);
  padding: 12px 14px 14px;
}
.plugin-detail .path-btn {
  width: 100%;
  margin-bottom: 10px;
  background: var(--code-bg);
}
.detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--text-secondary);
}
.tag.keyword {
  color: var(--primary);
  border-color: color-mix(in srgb, var(--primary) 25%, var(--border));
  background: color-mix(in srgb, var(--primary) 6%, transparent);
}
.link-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.link-list li {
  display: grid;
  grid-template-columns: 16px auto 1fr;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  margin-bottom: 6px;
  color: var(--text-secondary);
}
.link-list a {
  color: var(--primary);
  text-decoration: none;
  font-weight: 500;
}
.link-list a:hover {
  text-decoration: underline;
}
.link-list span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--mono);
  font-size: 11px;
}
.detail-block h3 {
  margin: 0 0 6px;
  font-size: 12px;
}
.detail-block ul {
  margin: 0 0 10px;
  padding: 0;
  list-style: none;
}
.detail-block li {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.detail-block code {
  font-family: var(--mono);
  font-size: 11px;
}
</style>
