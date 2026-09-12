<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/api/http'
import { t } from '@/i18n'
import { useAppStore } from '@/stores/app'
import type { PreviewProps } from '@/preview/types'

type SqliteColumn = {
  name: string
  type: string
  notnull: boolean
  pk: number
}

type SqliteTable = {
  name: string
  type: 'table' | 'view'
  row_count: number | null
  columns: SqliteColumn[]
}

type SqliteMeta = {
  path: string
  tables: SqliteTable[]
}

type SqliteCell = string | number | boolean | null | { $blob: number }

type SqliteRows = {
  table: string
  type: string
  offset: number
  limit: number
  total: number | null
  columns: string[]
  rows: SqliteCell[][]
}

const PAGE_SIZE = 100
const props = defineProps<PreviewProps>()
const store = useAppStore()

const error = ref('')
const loading = ref(true)
const rowsLoading = ref(false)
const tables = ref<SqliteTable[]>([])
const activeTable = ref('')
const columns = ref<string[]>([])
const columnMeta = ref<SqliteColumn[]>([])
const rows = ref<SqliteCell[][]>([])
const offset = ref(0)
const total = ref<number | null>(null)
const limit = ref(PAGE_SIZE)
let loadGen = 0

function errorMessage(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err)
  try {
    const parsed = JSON.parse(raw) as { message?: unknown }
    if (parsed && typeof parsed === 'object' && parsed.message) return String(parsed.message)
  } catch {
    /* keep raw */
  }
  return raw
}

function formatCount(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`
  return `${(n / 1_000_000).toFixed(1)}M`
}

function isBlob(cell: SqliteCell): cell is { $blob: number } {
  return Boolean(cell && typeof cell === 'object' && '$blob' in cell)
}

function formatBlob(size: number): string {
  if (size < 1024) return t('preview.sqliteBlob', { n: `${size} B` })
  if (size < 1024 * 1024) return t('preview.sqliteBlob', { n: `${(size / 1024).toFixed(1)} KB` })
  return t('preview.sqliteBlob', { n: `${(size / (1024 * 1024)).toFixed(1)} MB` })
}

function cellText(cell: SqliteCell): string {
  if (cell == null) return t('preview.sqliteNull')
  if (isBlob(cell)) return formatBlob(cell.$blob)
  return String(cell)
}

function cellClass(cell: SqliteCell): string {
  if (cell == null) return 'null'
  if (isBlob(cell)) return 'blob'
  if (typeof cell === 'number') return 'num'
  return ''
}

function columnType(name: string): string {
  return columnMeta.value.find((col) => col.name === name)?.type || ''
}

const activeMeta = computed(() => tables.value.find((item) => item.name === activeTable.value) || null)
const rangeFrom = computed(() => (rows.value.length ? offset.value + 1 : 0))
const rangeTo = computed(() => offset.value + rows.value.length)
const rangeLabel = computed(() => {
  if (!rows.value.length && !total.value) return t('preview.sqliteEmptyTable')
  if (total.value == null) return t('preview.sqliteRowsUnknown', { from: rangeFrom.value, to: rangeTo.value })
  return t('preview.sqliteRows', { from: rangeFrom.value, to: rangeTo.value, total: total.value })
})
const canPrev = computed(() => offset.value > 0)
const canNext = computed(() => {
  if (total.value != null) return offset.value + rows.value.length < total.value
  return rows.value.length >= limit.value
})

async function loadMeta() {
  const gen = ++loadGen
  const ws = store.workspaceId
  if (!ws) {
    error.value = t('preview.sqliteNoWorkspace')
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  tables.value = []
  rows.value = []
  columns.value = []
  try {
    const data = await api<SqliteMeta>(
      `/api/workspaces/${ws}/sqlite?path=${encodeURIComponent(props.path)}`,
    )
    if (gen !== loadGen) return
    tables.value = data.tables || []
    const first = tables.value[0]?.name || ''
    activeTable.value = first
    offset.value = 0
    if (first) await loadRows(gen)
    else loading.value = false
  } catch (err) {
    if (gen !== loadGen) return
    error.value = errorMessage(err)
    loading.value = false
  }
}

async function loadRows(gen = loadGen) {
  const ws = store.workspaceId
  const table = activeTable.value
  if (!ws || !table) {
    loading.value = false
    rowsLoading.value = false
    return
  }
  rowsLoading.value = true
  if (!loading.value) error.value = ''
  try {
    const data = await api<SqliteRows>(
      `/api/workspaces/${ws}/sqlite/rows?path=${encodeURIComponent(props.path)}` +
        `&table=${encodeURIComponent(table)}&offset=${offset.value}&limit=${PAGE_SIZE}`,
    )
    if (gen !== loadGen) return
    columns.value = data.columns || []
    rows.value = data.rows || []
    total.value = data.total ?? activeMeta.value?.row_count ?? null
    limit.value = data.limit || PAGE_SIZE
    columnMeta.value = activeMeta.value?.columns || []
  } catch (err) {
    if (gen !== loadGen) return
    error.value = errorMessage(err)
    rows.value = []
  } finally {
    if (gen === loadGen) {
      loading.value = false
      rowsLoading.value = false
    }
  }
}

function selectTable(name: string) {
  if (name === activeTable.value) return
  activeTable.value = name
  offset.value = 0
  void loadRows()
}

function pageBy(delta: number) {
  const next = Math.max(0, offset.value + delta * PAGE_SIZE)
  if (next === offset.value) return
  offset.value = next
  void loadRows()
}

onMounted(() => {
  void loadMeta()
})
watch(
  () => [props.path, store.workspaceId] as const,
  () => {
    void loadMeta()
  },
)
</script>

<template>
  <div class="preview-pane sqlite-preview">
    <p v-if="loading" class="status">{{ t('preview.sqlite') }}</p>
    <p v-else-if="error && !tables.length" class="status err">{{ error }}</p>
    <p v-else-if="!tables.length" class="status">{{ t('preview.sqliteEmpty') }}</p>
    <div v-else class="layout">
      <aside class="sidebar">
        <p class="side-label">{{ t('preview.sqliteTables') }}</p>
        <button
          v-for="item in tables"
          :key="item.name"
          type="button"
          class="table-btn"
          :class="{ on: item.name === activeTable }"
          :title="item.name"
          @click="selectTable(item.name)"
        >
          <span class="table-name">{{ item.name }}</span>
          <span class="table-meta">
            <em v-if="item.type === 'view'" class="kind">{{ t('preview.sqliteView') }}</em>
            <span class="count">{{ formatCount(item.row_count) }}</span>
          </span>
        </button>
      </aside>
      <section class="main">
        <div class="toolbar">
          <strong class="current">{{ activeTable }}</strong>
          <span class="range">{{ rangeLabel }}</span>
          <span class="spacer" />
          <button type="button" class="ghost-btn nav" :disabled="!canPrev || rowsLoading" @click="pageBy(-1)">
            {{ t('preview.prev') }}
          </button>
          <button type="button" class="ghost-btn nav" :disabled="!canNext || rowsLoading" @click="pageBy(1)">
            {{ t('preview.next') }}
          </button>
        </div>
        <p v-if="error" class="inline-err">{{ error }}</p>
        <div v-else-if="rowsLoading && !rows.length" class="status inner">{{ t('preview.sqlite') }}</div>
        <div v-else-if="columns.length" class="table-wrap" :class="{ dim: rowsLoading }">
          <table>
            <thead>
              <tr>
                <th v-for="col in columns" :key="col">
                  <span class="col-name">{{ col }}</span>
                  <span v-if="columnType(col)" class="col-type">{{ columnType(col) }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!rows.length">
                <td :colspan="columns.length" class="empty-row">{{ t('preview.sqliteEmptyTable') }}</td>
              </tr>
              <tr v-for="(row, ri) in rows" :key="ri">
                <td v-for="(cell, ci) in row" :key="ci" :class="cellClass(cell)">{{ cellText(cell) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="status inner">{{ t('preview.sqliteEmptyTable') }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.sqlite-preview {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--editor-bg);
}
.layout {
  flex: 1;
  min-height: 0;
  display: flex;
}
.sidebar {
  width: 188px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 6px;
  border-right: 1px solid var(--border);
  overflow: auto;
  background: var(--bg);
}
.side-label {
  margin: 0 6px 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-secondary);
}
.table-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--text-h);
  border-radius: var(--ghost-btn-radius);
  padding: 5px 8px;
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
}
.table-btn:hover:not(.on) {
  opacity: var(--ghost-hover-opacity);
}
.table-btn.on {
  color: var(--primary);
  background: var(--primary-soft);
}
.table-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--mono);
}
.table-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  color: var(--text-secondary);
  font-size: 11px;
}
.kind {
  font-style: normal;
  font-size: 10px;
  padding: 0 4px;
  border-radius: 4px;
  background: var(--bg-muted);
}
.count {
  font-variant-numeric: tabular-nums;
  font-family: var(--mono);
}
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.current {
  font-size: 13px;
  color: var(--text-h);
  font-family: var(--mono);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.range {
  font-size: 12px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.spacer {
  flex: 1;
}
.nav {
  padding: 0 10px;
}
.nav:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.table-wrap {
  flex: 1;
  overflow: auto;
}
.table-wrap.dim {
  opacity: 0.65;
}
table {
  border-collapse: collapse;
  font-size: 12.5px;
  font-family: var(--mono);
  min-width: 100%;
}
th,
td {
  border: 1px solid var(--border);
  padding: 4px 8px;
  white-space: nowrap;
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-h);
  vertical-align: top;
}
th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--bg-muted);
  font-weight: 600;
  text-align: left;
}
.col-name {
  display: block;
}
.col-type {
  display: block;
  margin-top: 1px;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--text-secondary);
  text-transform: uppercase;
}
td.null,
.empty-row {
  color: var(--text-secondary);
  font-style: italic;
}
td.blob {
  color: var(--text-secondary);
}
td.num {
  font-variant-numeric: tabular-nums;
}
tr:nth-child(even) td {
  background: var(--bg);
}
.empty-row {
  text-align: center;
  padding: 24px 8px;
}
.status {
  margin: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}
.status.inner {
  margin: 40px 24px;
}
.status.err,
.inline-err {
  color: var(--danger, #dc2626);
}
.inline-err {
  margin: 16px 12px;
  font-size: 13px;
}
</style>
