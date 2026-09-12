<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import { formatRelativeTime } from '@/utils/relativeTime'

type MemoryRow = {
  id: string
  kind: string
  subject: string
  content: Record<string, unknown>
  tags: string[]
  pinned?: boolean
  enabled?: boolean
  updated_at?: string | null
}

type RuleRow = {
  path: string
  title: string
  root?: boolean
  pinned: boolean
  enabled: boolean
}

const KIND_META: Record<string, { accent: string; icon: string }> = {
  profile: { accent: '#8b5cf6', icon: 'history' },
  preference: { accent: '#0891b2', icon: 'sliders' },
  goal: { accent: '#059669', icon: 'rocket' },
  context: { accent: '#0d9488', icon: 'globe' },
  workflow: { accent: '#6366f1', icon: 'gear' },
  decision: { accent: '#4f6bff', icon: 'check' },
  architecture: { accent: '#7c3aed', icon: 'tree' },
  convention: { accent: '#64748b', icon: 'book' },
  fact: { accent: '#475569', icon: 'file' },
  bug_fix: { accent: '#dc2626', icon: 'wrench' },
  lesson: { accent: '#d97706', icon: 'alert' },
  dependency: { accent: '#2563eb', icon: 'chip' },
  todo: { accent: '#ca8a04', icon: 'list' },
}

const { t } = useI18n()
const store = useAppStore()
const rows = ref<MemoryRow[]>([])
const rules = ref<RuleRow[]>([])
const loading = ref(false)
const error = ref('')
const query = ref('')
const kindFilter = ref('all')
const deletingId = ref<string | null>(null)

const workspaceId = computed(() => store.workspaceId)

const kindOptions = computed(() => {
  const set = new Set(rows.value.map((r) => r.kind))
  return ['all', ...[...set].sort()]
})

const stats = computed(() => {
  const total = rows.value.length
  const profile = rows.value.filter((r) => r.kind === 'profile').length
  return { total, profile }
})

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (kindFilter.value !== 'all' && r.kind !== kindFilter.value) return false
    if (!q) return true
    const stmt = String(r.content?.statement || '')
    const label = kindLabel(r.kind)
    return (
      r.subject.toLowerCase().includes(q) ||
      r.kind.toLowerCase().includes(q) ||
      label.toLowerCase().includes(q) ||
      stmt.toLowerCase().includes(q) ||
      (r.tags || []).some((tag) => tag.toLowerCase().includes(q))
    )
  })
})

function kindLabel(kind: string) {
  return t(`memory.kinds.${kind}`, kind)
}

function kindMeta(kind: string) {
  return KIND_META[kind] || { accent: '#64748b', icon: 'book' }
}

function statement(row: MemoryRow) {
  return String(row.content?.statement || '').trim()
}

function relatedPaths(row: MemoryRow): string[] {
  const paths = row.content?.related_paths
  return Array.isArray(paths) ? paths.map(String).filter(Boolean) : []
}

async function load() {
  if (!workspaceId.value) return
  loading.value = true
  error.value = ''
  try {
    const [mem, ruleData] = await Promise.all([
      api<{ memories: MemoryRow[] }>(`/api/workspaces/${workspaceId.value}/memories`),
      api<{ rules: RuleRow[] }>(`/api/workspaces/${workspaceId.value}/rules`).catch(() => ({ rules: [] })),
    ])
    rows.value = mem.memories || []
    rules.value = ruleData.rules || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function patchMemory(row: MemoryRow, body: { pinned?: boolean; enabled?: boolean }) {
  if (!workspaceId.value) return
  try {
    const updated = await api<MemoryRow>(`/api/workspaces/${workspaceId.value}/memories/${row.id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    rows.value = rows.value.map((item) => (item.id === row.id ? { ...item, ...updated } : item))
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

async function patchRule(row: RuleRow, body: { pinned?: boolean; enabled?: boolean }) {
  if (!workspaceId.value) return
  try {
    const updated = await api<RuleRow>(`/api/workspaces/${workspaceId.value}/rules`, {
      method: 'PATCH',
      body: JSON.stringify({ path: row.path, ...body }),
    })
    rules.value = rules.value.map((item) => (item.path === row.path ? { ...item, ...updated } : item))
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

async function remove(row: MemoryRow) {
  if (!workspaceId.value || deletingId.value) return
  deletingId.value = row.id
  try {
    await api(`/api/workspaces/${workspaceId.value}/memories/${row.id}`, { method: 'DELETE' })
    rows.value = rows.value.filter((r) => r.id !== row.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    deletingId.value = null
  }
}

watch(workspaceId, () => void load(), { immediate: true })
onMounted(() => void load())
</script>

<template>
  <div class="panel-shell memory-panel">
    <div class="panel-body">
      <header class="page-head">
        <div>
          <h1 class="page-title">{{ t('memory.title') }}</h1>
          <p class="page-lead">{{ t('memory.hint') }}</p>
        </div>
        <button type="button" class="btn btn-ghost" :disabled="loading" @click="load">
          <AppIcon name="refresh" :size="16" :stroke-width="1.75" />
          {{ t('common.refresh') }}
        </button>
      </header>

      <section class="tip-card">
        <span class="tip-icon"><AppIcon name="memory" :size="16" /></span>
        <div class="tip-copy">
          <strong>{{ t('memory.priorityTitle') }}</strong>
          <ol class="priority-list">
            <li>{{ t('memory.priorityUser') }}</li>
            <li>{{ t('memory.priorityRules') }}</li>
            <li>{{ t('memory.priorityPinned') }}</li>
            <li>{{ t('memory.prioritySoft') }}</li>
          </ol>
          <p>{{ t('memory.priorityWhy') }}</p>
        </div>
      </section>

      <section v-if="rules.length" class="rules-block">
        <h2>{{ t('memory.rulesTitle') }}</h2>
        <p class="rules-lead">{{ t('memory.rulesLead') }}</p>
        <article v-for="rule in rules" :key="rule.path" class="rule-row" :class="{ off: !rule.enabled }">
          <div>
            <strong>{{ rule.title }}</strong>
            <code>{{ rule.path }}</code>
          </div>
          <div class="rule-actions">
            <button
              type="button"
              class="ghost-icon-btn"
              :class="{ active: rule.pinned }"
              :title="rule.pinned ? t('memory.unpin') : t('memory.pin')"
              @click="patchRule(rule, { pinned: !rule.pinned })"
            >
              <AppIcon name="pin" :size="15" />
            </button>
            <button
              type="button"
              class="ghost-icon-btn"
              :class="{ active: !rule.enabled }"
              :title="rule.enabled ? t('memory.disable') : t('memory.enable')"
              @click="patchRule(rule, { enabled: !rule.enabled })"
            >
              <AppIcon name="ban" :size="15" />
            </button>
          </div>
        </article>
      </section>

      <div class="toolbar">
        <div class="search">
          <AppIcon name="search" :size="16" :stroke-width="1.75" />
          <input v-model="query" type="search" :placeholder="t('memory.search')" />
        </div>
        <div class="filters">
          <button
            v-for="kind in kindOptions"
            :key="kind"
            type="button"
            class="chip"
            :class="{ on: kindFilter === kind }"
            @click="kindFilter = kind"
          >
            {{ kind === 'all' ? t('memory.filterAll') : kindLabel(kind) }}
          </button>
        </div>
        <div class="stats">
          <span>{{ t('memory.statsTotal', { n: stats.total }) }}</span>
          <span v-if="stats.profile" class="profile-stat">{{ t('memory.statsProfile', { n: stats.profile }) }}</span>
        </div>
      </div>

      <p v-if="error" class="banner err">{{ error }}</p>
      <div v-else-if="loading && !rows.length" class="empty">
        <AppIcon name="memory" :size="28" />
        <p>{{ t('common.loading') }}</p>
      </div>
      <div v-else-if="!filtered.length" class="empty">
        <AppIcon name="memory" :size="28" />
        <p>{{ rows.length ? t('memory.noMatch') : t('memory.empty') }}</p>
        <small>{{ t('memory.emptyHint') }}</small>
      </div>

      <div v-else class="memory-grid">
        <article
          v-for="row in filtered"
          :key="row.id"
          class="memory-card"
          :class="{ off: row.enabled === false, pinned: row.pinned }"
          :style="{ '--accent': kindMeta(row.kind).accent }"
        >
          <div class="card-top">
            <span class="kind-icon">
              <AppIcon :name="kindMeta(row.kind).icon as any" :size="17" />
            </span>
            <div class="card-copy">
              <div class="card-title-row">
                <strong>{{ row.subject }}</strong>
                <span class="kind-pill">{{ kindLabel(row.kind) }}</span>
                <span v-if="row.pinned" class="kind-pill pin">{{ t('memory.pinned') }}</span>
                <span v-if="row.enabled === false" class="kind-pill off">{{ t('memory.disabled') }}</span>
              </div>
              <p class="statement">{{ statement(row) }}</p>
            </div>
            <div class="card-btns">
              <button
                type="button"
                class="card-delete-btn ghost-icon-btn"
                :class="{ active: row.pinned }"
                :title="row.pinned ? t('memory.unpin') : t('memory.pin')"
                @click="patchMemory(row, { pinned: !row.pinned })"
              >
                <AppIcon name="pin" :size="16" :stroke-width="1.75" />
              </button>
              <button
                type="button"
                class="card-delete-btn ghost-icon-btn"
                :class="{ active: row.enabled === false }"
                :title="row.enabled === false ? t('memory.enable') : t('memory.disable')"
                @click="patchMemory(row, { enabled: row.enabled === false })"
              >
                <AppIcon name="ban" :size="16" :stroke-width="1.75" />
              </button>
              <button
                type="button"
                class="card-delete-btn ghost-icon-btn danger"
                :title="t('common.delete')"
                :disabled="deletingId === row.id"
                @click="remove(row)"
              >
                <AppIcon name="trash" :size="16" :stroke-width="1.75" />
              </button>
            </div>
          </div>

          <div class="card-foot">
            <div v-if="row.tags?.length" class="tags">
              <span v-for="tag in row.tags" :key="tag" class="tag">#{{ tag }}</span>
            </div>
            <div v-if="relatedPaths(row).length" class="paths">
              <AppIcon name="file" :size="12" />
              <span>{{ relatedPaths(row).join(' · ') }}</span>
            </div>
            <time v-if="row.updated_at" class="time">{{ formatRelativeTime(row.updated_at) }}</time>
          </div>
        </article>
      </div>
    </div>
  </div>
</template>

<style scoped>
.memory-panel .panel-body {
  padding: 18px 20px 28px;
  overflow: auto;
  height: 100%;
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
  max-width: 52ch;
}
.tip-card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 14px;
  margin-bottom: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, #8b5cf6 6%, var(--panel-bg));
}
.tip-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  color: #8b5cf6;
  background: color-mix(in srgb, #8b5cf6 14%, transparent);
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
.priority-list {
  margin: 6px 0 8px;
  padding-left: 18px;
  font-size: 12.5px;
  color: var(--text-h);
  line-height: 1.55;
}
.rules-block {
  margin-bottom: 18px;
}
.rules-block h2 {
  margin: 0 0 4px;
  font-size: 13px;
  color: var(--text-h);
}
.rules-lead {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--text-secondary);
}
.rule-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 6px;
}
.rule-row.off { opacity: 0.55; }
.rule-row strong { display: block; font-size: 13px; color: var(--text-h); }
.rule-row code { font-size: 11px; color: var(--text-muted); }
.rule-actions { display: flex; gap: 4px; }

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
  max-width: 100%;
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
  font-size: 12px;
  color: var(--text-muted);
  margin-left: auto;
}
.profile-stat {
  color: #8b5cf6;
}

.banner.err {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid color-mix(in srgb, var(--danger) 35%, var(--border));
  background: color-mix(in srgb, var(--danger) 8%, var(--panel-bg));
  color: var(--danger);
  font-size: 13px;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 48px 20px;
  text-align: center;
  color: var(--text-muted);
}
.empty p {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}
.empty small {
  max-width: 36ch;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
}

.memory-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.memory-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  padding: 12px 14px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.memory-card:hover {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  box-shadow: 0 1px 0 color-mix(in srgb, var(--accent) 8%, transparent);
}
.memory-card.off { opacity: 0.62; }
.kind-pill.pin { color: #d97706; }
.kind-pill.off { color: var(--text-muted); }
.card-btns { display: flex; gap: 2px; flex-shrink: 0; }

.card-top {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.kind-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
}
.card-copy {
  flex: 1;
  min-width: 0;
}
.card-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.card-title-row strong {
  font-size: 14px;
  color: var(--text-h);
}
.kind-pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 25%, var(--border));
}
.statement {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-secondary);
}

.card-delete-btn {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.memory-card:hover .card-delete-btn,
.card-delete-btn:focus-visible,
.card-delete-btn.active {
  opacity: 1;
}
.card-delete-btn:disabled {
  opacity: 0.5;
  cursor: wait;
}

.card-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  background: var(--surface-2, var(--bg));
  color: var(--text-muted);
  font-family: var(--mono, ui-monospace, monospace);
}
.paths {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: var(--text-muted);
  font-family: var(--mono, ui-monospace, monospace);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.time {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
}
</style>
