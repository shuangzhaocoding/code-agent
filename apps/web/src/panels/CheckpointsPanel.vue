<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import { formatRelativeTime } from '@/utils/relativeTime'

type FileRow = {
  path: string
  action: string
  block_type?: string
  before_chars?: number
  after_chars?: number
  before?: string
  after?: string
}

type Checkpoint = {
  run_id: string
  status: string
  mode: string
  started_at?: string | null
  ended_at?: string | null
  file_count: number
  files: FileRow[]
  skill_name?: string | null
}

const { t } = useI18n()
const store = useAppStore()
const loading = ref(false)
const restoring = ref(false)
const error = ref('')
const notice = ref('')
const checkpoints = ref<Checkpoint[]>([])
const selectedId = ref<string | null>(null)
const detail = ref<Checkpoint | null>(null)
const selectedPaths = ref<Set<string>>(new Set())

const selected = computed(
  () => checkpoints.value.find((c) => c.run_id === selectedId.value) || checkpoints.value[0] || null,
)

async function load() {
  const cid = store.conversationId
  if (!cid) {
    checkpoints.value = []
    selectedId.value = null
    detail.value = null
    return
  }
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    const data = await api<{ checkpoints: Checkpoint[] }>(`/api/conversations/${cid}/checkpoints`)
    checkpoints.value = data.checkpoints || []
    if (!selectedId.value || !checkpoints.value.some((c) => c.run_id === selectedId.value)) {
      selectedId.value = checkpoints.value[0]?.run_id || null
    }
    if (selectedId.value) await loadDetail(selectedId.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function loadDetail(runId: string) {
  selectedId.value = runId
  selectedPaths.value = new Set()
  try {
    detail.value = await api<Checkpoint>(`/api/runs/${runId}/checkpoints`)
    selectedPaths.value = new Set((detail.value.files || []).map((f) => f.path))
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

function togglePath(path: string) {
  const next = new Set(selectedPaths.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  selectedPaths.value = next
}

function selectAll(on: boolean) {
  if (!detail.value) return
  selectedPaths.value = on ? new Set(detail.value.files.map((f) => f.path)) : new Set()
}

async function restore(mode: 'run' | 'to_before') {
  if (!selectedId.value || restoring.value) return
  const paths = [...selectedPaths.value]
  if (!paths.length) {
    error.value = t('checkpoints.noPaths')
    return
  }
  const confirmMsg =
    mode === 'to_before' ? t('checkpoints.confirmToBefore') : t('checkpoints.confirmRun')
  if (!window.confirm(confirmMsg)) return

  restoring.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await api<{
      ok: boolean
      files_reverted: number
      reverted_paths: string[]
      warnings: string[]
    }>(`/api/runs/${selectedId.value}/checkpoints/restore`, {
      method: 'POST',
      body: JSON.stringify({ mode, paths }),
    })
    notice.value = t('checkpoints.restored', { n: result.files_reverted || 0 })
    if (result.warnings?.length) {
      error.value = result.warnings.join('\n')
    }
    // Refresh open editors if any restored path is open
    for (const path of result.reverted_paths || []) {
      const open = store.openFiles.find((f) => f.path === path)
      if (open) {
        await store.openAgentFile(path).catch(() => undefined)
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    restoring.value = false
  }
}

function actionLabel(action: string) {
  if (action === 'create') return t('checkpoints.actionCreate')
  if (action === 'delete') return t('checkpoints.actionDelete')
  return t('checkpoints.actionEdit')
}

watch(
  () => [store.conversationId, store.runStatus] as const,
  () => {
    if (store.runStatus === 'completed' || store.runStatus === 'failed' || store.runStatus === 'cancelled') {
      void load()
    } else {
      void load()
    }
  },
  { immediate: true },
)
onMounted(() => void load())
</script>

<template>
  <div class="panel-shell checkpoints-panel">
    <div class="panel-body">
      <header class="page-head">
        <div>
          <h1 class="page-title">{{ t('checkpoints.title') }}</h1>
          <p class="page-lead">{{ t('checkpoints.hint') }}</p>
        </div>
        <button type="button" class="btn btn-ghost" :disabled="loading" @click="load">
          <AppIcon name="refresh" :size="16" :stroke-width="1.75" />
          {{ t('common.refresh') }}
        </button>
      </header>

      <p v-if="!store.conversationId" class="empty">{{ t('checkpoints.noConversation') }}</p>
      <p v-else-if="error && !checkpoints.length" class="banner err">{{ error }}</p>
      <div v-else-if="loading && !checkpoints.length" class="empty">
        <AppIcon name="loader" :size="28" />
        <p>{{ t('common.loading') }}</p>
      </div>
      <div v-else-if="!checkpoints.length" class="empty">
        <AppIcon name="history" :size="28" />
        <p>{{ t('checkpoints.empty') }}</p>
        <small>{{ t('checkpoints.emptyHint') }}</small>
      </div>

      <template v-else>
        <div class="layout">
          <aside class="timeline">
            <button
              v-for="cp in checkpoints"
              :key="cp.run_id"
              type="button"
              class="cp-item"
              :class="{ on: selected?.run_id === cp.run_id }"
              @click="loadDetail(cp.run_id)"
            >
              <div class="cp-top">
                <span class="dot" />
                <strong>{{ cp.started_at ? formatRelativeTime(cp.started_at) : cp.run_id.slice(0, 8) }}</strong>
                <span class="muted">{{ cp.mode }}</span>
              </div>
              <div class="cp-meta">
                <span>{{ t('checkpoints.fileCount', { n: cp.file_count }) }}</span>
                <span class="status">{{ cp.status }}</span>
              </div>
            </button>
          </aside>

          <section v-if="detail" class="detail">
            <header class="detail-head">
              <div>
                <h2>{{ t('checkpoints.detailTitle') }}</h2>
                <p class="muted">
                  {{ detail.started_at || detail.run_id }}
                  · {{ t('checkpoints.fileCount', { n: detail.file_count }) }}
                </p>
              </div>
              <div class="actions">
                <button type="button" class="btn btn-ghost" @click="selectAll(true)">{{ t('checkpoints.selectAll') }}</button>
                <button type="button" class="btn btn-ghost" @click="selectAll(false)">{{ t('checkpoints.selectNone') }}</button>
              </div>
            </header>

            <p v-if="notice" class="banner ok">{{ notice }}</p>
            <p v-if="error" class="banner err">{{ error }}</p>

            <div class="files">
              <label v-for="file in detail.files" :key="file.path" class="file-row">
                <input
                  type="checkbox"
                  :checked="selectedPaths.has(file.path)"
                  @change="togglePath(file.path)"
                />
                <div class="file-copy">
                  <code>{{ file.path }}</code>
                  <span class="muted">
                    {{ actionLabel(file.action) }}
                    · {{ file.before_chars || 0 }} → {{ file.after_chars || 0 }} chars
                  </span>
                </div>
              </label>
            </div>

            <footer class="restore-bar">
              <button
                type="button"
                class="btn btn-primary"
                :disabled="restoring || !selectedPaths.size"
                @click="restore('run')"
              >
                <AppIcon name="history" :size="15" />
                {{ t('checkpoints.restoreRun') }}
              </button>
              <button
                type="button"
                class="btn btn-ghost"
                :disabled="restoring || !selectedPaths.size"
                @click="restore('to_before')"
              >
                {{ t('checkpoints.restoreToBefore') }}
              </button>
              <p class="hint">{{ t('checkpoints.restoreHint') }}</p>
            </footer>
          </section>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.checkpoints-panel {
  height: 100%;
  min-height: 0;
}
.panel-body {
  height: 100%;
  overflow: auto;
  padding: 16px 18px 28px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.page-title {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
}
.page-lead {
  margin: 4px 0 0;
  color: var(--ca-muted, #8b93a7);
  font-size: 12.5px;
  line-height: 1.45;
}
.layout {
  display: grid;
  grid-template-columns: minmax(180px, 240px) 1fr;
  gap: 14px;
  min-height: 0;
  flex: 1;
}
.timeline {
  display: flex;
  flex-direction: column;
  gap: 6px;
  border-right: 1px solid var(--ca-border, #2a3142);
  padding-right: 10px;
  overflow: auto;
}
.cp-item {
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  color: inherit;
  border-radius: 10px;
  padding: 10px;
  cursor: pointer;
}
.cp-item.on {
  border-color: var(--ca-accent, #f59e0b);
  background: color-mix(in srgb, var(--ca-accent, #f59e0b) 10%, transparent);
}
.cp-top {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ca-accent, #f59e0b);
  flex-shrink: 0;
}
.cp-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 11px;
  color: var(--ca-muted, #8b93a7);
  padding-left: 16px;
}
.detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}
.detail-head h2 {
  margin: 0;
  font-size: 14px;
}
.actions {
  display: flex;
  gap: 6px;
}
.files {
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid var(--ca-border, #2a3142);
  border-radius: 12px;
  padding: 8px;
  max-height: 420px;
  overflow: auto;
}
.file-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
}
.file-row:hover {
  background: color-mix(in srgb, var(--ca-fg, #fff) 4%, transparent);
}
.file-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.file-copy code {
  font-size: 12.5px;
  word-break: break-all;
}
.restore-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding-top: 4px;
}
.hint {
  margin: 0;
  width: 100%;
  font-size: 12px;
  color: var(--ca-muted, #8b93a7);
}
.muted {
  color: var(--ca-muted, #8b93a7);
  font-size: 12px;
}
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 48px 16px;
  color: var(--ca-muted, #8b93a7);
  text-align: center;
}
.banner.err {
  color: #f87171;
  font-size: 13px;
  white-space: pre-wrap;
}
.banner.ok {
  color: #34d399;
  font-size: 13px;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 8px;
  border: 1px solid var(--ca-border, #2a3142);
  background: transparent;
  color: inherit;
  padding: 6px 10px;
  font-size: 12.5px;
  cursor: pointer;
}
.btn-primary {
  background: color-mix(in srgb, var(--ca-accent, #f59e0b) 22%, transparent);
  border-color: color-mix(in srgb, var(--ca-accent, #f59e0b) 50%, transparent);
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
@media (max-width: 860px) {
  .layout {
    grid-template-columns: 1fr;
  }
  .timeline {
    border-right: 0;
    border-bottom: 1px solid var(--ca-border, #2a3142);
    padding-right: 0;
    padding-bottom: 10px;
    flex-direction: row;
    overflow-x: auto;
  }
  .cp-item {
    min-width: 160px;
  }
}
</style>
