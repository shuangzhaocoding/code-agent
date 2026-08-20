<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import * as XLSX from 'xlsx'
import type { PreviewProps } from '@/preview/types'

const props = defineProps<PreviewProps>()
const error = ref('')
const loading = ref(true)
const sheetNames = ref<string[]>([])
const activeSheet = ref('')
const rows = ref<string[][]>([])
let workbookCache: XLSX.WorkBook | null = null

function renderSheet(wb: XLSX.WorkBook, name: string) {
  const sheet = wb.Sheets[name]
  if (!sheet) {
    rows.value = []
    return
  }
  const data = XLSX.utils.sheet_to_json<(string | number | boolean | null)[]>(sheet, {
    header: 1,
    defval: '',
    raw: false,
  })
  rows.value = data.map((row) => row.map((cell) => (cell == null ? '' : String(cell))))
}

async function loadAndCache() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(props.previewUrl)
    if (!res.ok) throw new Error(await res.text())
    const buf = await res.arrayBuffer()
    workbookCache = XLSX.read(buf, { type: 'array' })
    sheetNames.value = workbookCache.SheetNames
    activeSheet.value = workbookCache.SheetNames[0] || ''
    renderSheet(workbookCache, activeSheet.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    rows.value = []
    sheetNames.value = []
    workbookCache = null
  } finally {
    loading.value = false
  }
}

function onSelectSheet(name: string) {
  activeSheet.value = name
  if (workbookCache) renderSheet(workbookCache, name)
}

const hasTable = computed(() => rows.value.length > 0)

onMounted(() => {
  void loadAndCache()
})
watch(
  () => props.previewUrl,
  () => {
    void loadAndCache()
  },
)
</script>

<template>
  <div class="preview-pane xlsx-preview">
    <p v-if="loading" class="status">正在解析表格…</p>
    <p v-else-if="error" class="status err">{{ error }}</p>
    <template v-else>
      <div v-if="sheetNames.length > 1" class="sheets">
        <button
          v-for="name in sheetNames"
          :key="name"
          type="button"
          class="sheet-btn"
          :class="{ on: name === activeSheet }"
          @click="onSelectSheet(name)"
        >
          {{ name }}
        </button>
      </div>
      <div v-if="hasTable" class="table-wrap">
        <table>
          <tbody>
            <tr v-for="(row, ri) in rows" :key="ri">
              <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="status">空表格</p>
    </template>
  </div>
</template>

<style scoped>
.xlsx-preview {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--editor-bg);
}
.sheets {
  display: flex;
  gap: 4px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  flex-shrink: 0;
}
.sheet-btn {
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.sheet-btn.on {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}
.table-wrap {
  flex: 1;
  overflow: auto;
  padding: 0;
}
table {
  border-collapse: collapse;
  font-size: 12.5px;
  font-family: var(--mono);
  min-width: 100%;
}
td {
  border: 1px solid var(--border);
  padding: 4px 8px;
  white-space: nowrap;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-h);
}
tr:nth-child(odd) td {
  background: var(--bg);
}
tr:first-child td {
  font-weight: 600;
  background: var(--bg-muted);
}
.status {
  margin: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}
.status.err {
  color: var(--danger, #dc2626);
}
</style>
