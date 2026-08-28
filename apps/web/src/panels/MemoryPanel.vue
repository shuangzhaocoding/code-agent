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
  updated_at?: string | null
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
    const data = await api<{ memories: MemoryRow[] }>(`/api/workspaces/${workspaceId.value}/memories`)
    rows.value = data.memories || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
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
          <AppIcon name="refresh" :size="13" />
          {{ t('common.refresh') }}
        </button>
      </header>

      <section class="tip-card">
        <span class="tip-icon"><AppIcon name="memory" :size="16" /></span>
        <div class="tip-copy">
          <strong>{{ t('memory.tipTitle') }}</strong>
          <p>{{ t('memory.tipBody') }}</p>
        </div>
      </section>

      <div class="toolbar">
        <div class="search">
          <AppIcon name="search" :size="14" />
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
              </div>
              <p class="statement">{{ statement(row) }}</p>
            </div>
            <button
              type="button"
              class="icon-btn"
              :title="t('common.delete')"
              :disabled="deletingId === row.id"
              @click="remove(row)"
            >
              <AppIcon name="trash" :size="14" />
            </button>
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
.page-head .btn {
  height: 26px;
  padding: 0 10px;
  font-size: 12px;
  gap: 5px;
  flex-shrink: 0;
}

.btn-ghost {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 12.5px;
  cursor: pointer;
  flex-shrink: 0;
}
.btn-ghost:hover:not(:disabled) {
  color: var(--text-h);
  border-color: color-mix(in srgb, var(--primary) 30%, var(--border));
}
.btn-ghost:disabled {
  opacity: 0.55;
  cursor: not-allowed;
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
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}
.chip.on {
  background: var(--primary-soft);
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  color: var(--primary);
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

.icon-btn {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
}
.memory-card:hover .icon-btn,
.icon-btn:focus-visible {
  opacity: 1;
}
.icon-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  color: var(--danger);
}
.icon-btn:disabled {
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
