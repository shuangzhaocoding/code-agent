<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'

type SkillItem = {
  name: string
  description: string
  source: string
  path: string
  enabled?: boolean
  invalid_reason?: string | null
}

type SkillDetail = SkillItem & {
  body?: string
  license?: string
  metadata?: Record<string, unknown>
}

const store = useAppStore()
const query = ref('')
const sourceFilter = ref<string>('all')
const loading = ref(false)
const expanded = ref<string | null>(null)
const detail = ref<SkillDetail | null>(null)
const detailLoading = ref(false)
const copied = ref<string | null>(null)

const SOURCE_META: Record<string, { label: string; accent: string }> = {
  bundled: { label: '内置', accent: '#4f6bff' },
  user: { label: '用户', accent: '#0891b2' },
  workspace: { label: '工作区', accent: '#059669' },
  agents: { label: 'Agents', accent: '#0d9488' },
  cursor: { label: 'Cursor', accent: '#64748b' },
}

const skills = computed(() => (store.skills || []) as SkillItem[])

const sources = computed(() => {
  const set = new Set(skills.value.map((s) => s.source))
  return ['all', ...[...set].sort()]
})

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return skills.value.filter((s) => {
    if (sourceFilter.value !== 'all' && s.source !== sourceFilter.value) return false
    if (!q) return true
    const hay = `${s.name} ${s.description} ${s.source} ${s.path}`.toLowerCase()
    return hay.includes(q)
  })
})

const stats = computed(() => {
  const total = skills.value.length
  const bad = skills.value.filter((s) => s.invalid_reason).length
  return { total, ok: total - bad, bad }
})

function sourceMeta(source: string) {
  return SOURCE_META[source] || { label: source, accent: '#64748b' }
}

function sourceLabel(source: string) {
  if (source === 'all') return '全部'
  return sourceMeta(source).label
}

function sKey(skill: SkillItem) {
  return `${skill.source}:${skill.name}`
}

async function refresh() {
  loading.value = true
  try {
    await store.loadSkills()
  } finally {
    loading.value = false
  }
}

async function toggleDetail(skill: SkillItem) {
  const key = sKey(skill)
  if (expanded.value === key) {
    expanded.value = null
    detail.value = null
    return
  }
  expanded.value = key
  detail.value = null
  detailLoading.value = true
  try {
    const q = store.workspaceId ? `?workspace_id=${store.workspaceId}` : ''
    detail.value = await api<SkillDetail>(`/api/skills/${encodeURIComponent(skill.name)}${q}`)
  } catch {
    detail.value = { ...skill, body: '', invalid_reason: skill.invalid_reason || '加载失败' }
  } finally {
    detailLoading.value = false
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
  <div class="panel-shell skills-panel">
    <div class="panel-body">
      <header class="page-head">
        <div>
          <h1 class="page-title">Skill</h1>
          <p class="page-lead">Agent 可按任务自动加载的指令包。放好目录后刷新即可发现。</p>
        </div>
        <button type="button" class="btn btn-ghost" :disabled="loading" @click="refresh">
          <AppIcon name="refresh" :size="15" />
          刷新
        </button>
      </header>

      <section class="tip-card">
        <span class="tip-icon"><AppIcon name="puzzle" :size="16" /></span>
        <div class="tip-copy">
          <strong>安装位置</strong>
          <p>
            仓库 <code>skills/</code>
            · 用户 <code>~/.code-agent/skills/</code>
            · 工作区 <code>.agents/skills/</code>
            · <code>.code-agent/skills/</code>
            · <code>.cursor/skills/</code>
          </p>
        </div>
      </section>

      <div class="toolbar">
        <div class="search">
          <AppIcon name="search" :size="14" />
          <input v-model="query" type="search" placeholder="搜索名称、描述或路径" />
        </div>
        <div class="filters">
          <button
            v-for="src in sources"
            :key="src"
            type="button"
            class="chip"
            :class="{ on: sourceFilter === src }"
            @click="sourceFilter = src"
          >
            {{ sourceLabel(src) }}
          </button>
        </div>
        <div class="stats">
          <span>{{ stats.ok }} 可用</span>
          <span v-if="stats.bad" class="bad">{{ stats.bad }} 异常</span>
          <span class="muted">共 {{ stats.total }}</span>
        </div>
      </div>

      <div v-if="!filtered.length" class="empty">
        <AppIcon name="puzzle" :size="28" />
        <p>{{ skills.length ? '没有匹配的 Skill' : '还没有发现 Skill' }}</p>
        <small>每个 Skill 是一个包含 SKILL.md 的目录，目录名需与 name 一致。</small>
      </div>

      <div v-else class="skill-grid">
        <article
          v-for="s in filtered"
          :key="sKey(s)"
          class="skill-card"
          :class="{ open: expanded === sKey(s), invalid: !!s.invalid_reason }"
        >
          <button type="button" class="skill-main" @click="toggleDetail(s)">
            <span class="skill-icon" :style="{ '--accent': sourceMeta(s.source).accent }">
              <AppIcon name="puzzle" :size="18" />
            </span>
            <span class="skill-copy">
              <span class="skill-title-row">
                <strong>{{ s.name }}</strong>
                <span class="source-pill" :style="{ '--accent': sourceMeta(s.source).accent }">
                  {{ sourceMeta(s.source).label }}
                </span>
              </span>
              <span class="skill-desc">{{ s.description || '暂无描述' }}</span>
            </span>
            <AppIcon class="chevron" name="chevron-right" :size="16" />
          </button>

          <div class="skill-meta">
            <button type="button" class="path-btn" :title="s.path" @click.stop="copyPath(s.path)">
              <AppIcon name="file" :size="12" />
              <span>{{ s.path }}</span>
              <em>{{ copied === s.path ? '已复制' : '复制路径' }}</em>
            </button>
            <span v-if="s.invalid_reason" class="status bad">{{ s.invalid_reason }}</span>
            <span v-else class="status ok">可用</span>
          </div>

          <div v-if="expanded === sKey(s)" class="skill-detail">
            <p v-if="detailLoading" class="detail-loading">加载中…</p>
            <template v-else-if="detail">
              <div v-if="detail.license || detail.metadata" class="detail-tags">
                <span v-if="detail.license" class="tag">License · {{ detail.license }}</span>
                <span v-if="detail.metadata?.version" class="tag">v{{ detail.metadata.version }}</span>
                <span v-if="detail.metadata?.author" class="tag">{{ detail.metadata.author }}</span>
              </div>
              <pre class="body">{{ detail.body || '（无正文）' }}</pre>
            </template>
          </div>
        </article>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skills-panel .panel-body {
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
  margin-bottom: 2px;
}
.tip-copy p {
  margin: 0;
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
  color: var(--text-h);
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
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
}
.chip.on {
  background: var(--primary-soft);
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  color: var(--primary);
}
.stats {
  display: flex;
  gap: 10px;
  margin-left: auto;
  font-size: 12px;
  color: var(--text-h);
}
.stats .muted { color: var(--text-secondary); }
.stats .bad { color: var(--error-text); }

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
.empty small { font-size: 12px; }

.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.skill-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  overflow: hidden;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.skill-card:hover {
  border-color: color-mix(in srgb, var(--primary) 28%, var(--border));
}
.skill-card.open {
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary) 12%, transparent);
}
.skill-card.invalid {
  border-color: color-mix(in srgb, #ef4444 35%, var(--border));
}

.skill-main {
  display: grid;
  grid-template-columns: 40px 1fr 16px;
  gap: 10px;
  align-items: start;
  width: 100%;
  padding: 14px 14px 8px;
  border: 0;
  background: transparent;
  text-align: left;
  color: inherit;
  cursor: pointer;
}
.skill-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.skill-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.skill-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.skill-title-row strong {
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
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 22%, transparent);
}
.skill-desc {
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.chevron {
  margin-top: 10px;
  color: var(--text-secondary);
  opacity: 0.7;
  transition: transform 0.15s;
}
.skill-card.open .chevron {
  transform: rotate(90deg);
}

.skill-meta {
  display: flex;
  align-items: center;
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
.path-btn:hover {
  border-color: var(--border);
  color: var(--text-h);
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
  flex-shrink: 0;
}
.status {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
}
.status.ok {
  color: #059669;
  background: color-mix(in srgb, #10b981 12%, transparent);
}
.status.bad {
  color: var(--error-text);
  background: color-mix(in srgb, #ef4444 12%, transparent);
}

.skill-detail {
  border-top: 1px solid var(--border);
  padding: 12px 14px 14px;
  background: color-mix(in srgb, var(--bg) 70%, var(--panel-bg));
}
.detail-loading {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
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
  background: var(--panel-bg);
}
.body {
  margin: 0;
  max-height: 280px;
  overflow: auto;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--panel-bg);
  color: var(--text);
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-h);
  border-radius: var(--radius-sm);
  padding: 7px 12px;
  font-size: 12.5px;
  cursor: pointer;
}
.btn-ghost:hover {
  background: var(--bg-muted, var(--code-bg));
}
.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>
