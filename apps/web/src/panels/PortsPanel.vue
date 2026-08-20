<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'

type PortItem = {
  port: number
  address: string
  pid: number | null
  process: string | null
  cmdline: string | null
  url: string
  preview_path: string
  connect_host?: string
  reachable?: boolean
  self?: boolean
}

const store = useAppStore()
const ports = ref<PortItem[]>([])
const error = ref('')
const loading = ref(false)
const killing = ref<number | null>(null)
const query = ref('')
const previewPort = ref<number | null>(null)
const autoRefresh = ref(true)
let timer: ReturnType<typeof setInterval> | null = null

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return ports.value
  return ports.value.filter((p) => {
    const hay = `${p.port} ${p.address} ${p.process || ''} ${p.cmdline || ''} ${p.pid || ''}`.toLowerCase()
    return hay.includes(q)
  })
})

const previewUrl = computed(() =>
  previewPort.value != null ? `/api/preview/${previewPort.value}/` : null,
)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const data = await api<{ ports: PortItem[] }>('/api/ports')
    ports.value = data.ports || []
    if (previewPort.value != null && !ports.value.some((p) => p.port === previewPort.value)) {
      previewPort.value = null
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

function openExternal(item: PortItem) {
  if (!item.self) {
    window.open(item.preview_path, '_blank', 'noopener,noreferrer')
    return
  }
  window.open(item.url, '_blank', 'noopener,noreferrer')
}

async function copyUrl(item: PortItem) {
  try {
    await navigator.clipboard.writeText(item.url)
  } catch {
    error.value = '复制失败'
  }
}

function openPreview(item: PortItem) {
  if (item.self) return
  previewPort.value = item.port
}

function closePreview() {
  previewPort.value = null
}

async function killPort(item: PortItem) {
  if (item.self || !item.pid) return
  const ok = await store.askConfirm({
    title: '结束端口进程',
    summary: `结束监听 ${item.port} 的进程？\n${item.process || 'unknown'} (pid ${item.pid})`,
    details: item.cmdline || undefined,
    confirmLabel: '结束进程',
    cancelLabel: '取消',
    danger: true,
  })
  if (!ok) return

  killing.value = item.port
  error.value = ''
  try {
    await api(`/api/ports/${item.port}`, { method: 'DELETE' })
    if (previewPort.value === item.port) previewPort.value = null
    await refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    killing.value = null
  }
}

function startTimer() {
  stopTimer()
  if (!autoRefresh.value) return
  timer = setInterval(() => {
    void refresh()
  }, 3000)
}

function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(() => {
  void refresh()
  startTimer()
})

onUnmounted(stopTimer)

function onToggleAuto() {
  autoRefresh.value = !autoRefresh.value
  startTimer()
}
</script>

<template>
  <div class="panel-shell ports panel-chromeless">
    <div class="ports-bar">
      <span class="title">
        <AppIcon name="globe" :size="14" />
        端口
        <span class="count">{{ filtered.length }}</span>
      </span>
      <span class="spacer" />
      <label class="auto">
        <input type="checkbox" :checked="autoRefresh" @change="onToggleAuto" />
        自动刷新
      </label>
      <button type="button" class="icon-btn icon-btn-ghost" title="刷新" :disabled="loading" @click="refresh">
        <AppIcon name="refresh" :size="14" />
      </button>
    </div>

    <div class="search">
      <AppIcon name="search" :size="14" />
      <input v-model="query" type="search" placeholder="搜索端口 / 进程" />
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="body" :class="{ split: previewUrl }">
      <div class="list">
        <button
          v-for="item in filtered"
          :key="`${item.address}:${item.port}`"
          type="button"
          class="row"
          :class="{ on: previewPort === item.port, self: item.self }"
          @click="openPreview(item)"
          @dblclick="openExternal(item)"
        >
          <span class="port">{{ item.port }}</span>
          <span class="meta">
            <span class="process">
              {{ item.process || 'unknown' }}
              <span v-if="item.self" class="tag">本服务</span>
            </span>
            <span class="addr">{{ item.address }} · {{ item.connect_host || '127.0.0.1' }} · pid {{ item.pid ?? '—' }}</span>
          </span>
          <span class="actions" @click.stop>
            <button type="button" class="icon-btn icon-btn-ghost" title="通过代理打开（推荐）" @click="openExternal(item)">
              <AppIcon name="globe" :size="13" />
            </button>
            <button type="button" class="icon-btn icon-btn-ghost" :title="`复制本机地址 ${item.url}`" @click="copyUrl(item)">
              <AppIcon name="file" :size="13" />
            </button>
            <button
              type="button"
              class="icon-btn icon-btn-ghost"
              title="面板预览"
              :disabled="item.self"
              @click="openPreview(item)"
            >
              <AppIcon name="eye" :size="13" />
            </button>
            <button
              type="button"
              class="icon-btn icon-btn-ghost danger"
              title="结束进程"
              :disabled="item.self || !item.pid || killing === item.port"
              @click="killPort(item)"
            >
              <AppIcon name="trash" :size="13" />
            </button>
          </span>
        </button>
        <p v-if="!loading && !filtered.length" class="empty">暂无本机可访问的监听端口</p>
      </div>

      <div v-if="previewUrl" class="preview">
        <div class="preview-bar">
          <span>预览 · {{ previewPort }}</span>
          <span class="hint">前端 + 后端都走代理：/api 或 localhost:后端端口 会自动转发</span>
          <span class="spacer" />
          <a class="link" :href="previewUrl" target="_blank" rel="noopener">新标签打开</a>
          <button type="button" class="icon-btn icon-btn-ghost" title="关闭预览" @click="closePreview">×</button>
        </div>
        <iframe class="frame" :src="previewUrl" title="Port preview" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.ports {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}
.ports-bar,
.preview-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
}
.count {
  font-weight: 500;
  color: var(--text-secondary);
  font-size: 12px;
}
.spacer { flex: 1; }
.auto {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  user-select: none;
}
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 12px 0;
  padding: 0 10px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text-secondary);
  flex-shrink: 0;
}
.search input {
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-h);
  font-size: 13px;
}
.err {
  margin: 8px 12px 0;
  color: var(--error-text);
  font-size: 12px;
}
.body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.body.split {
  flex-direction: row;
}
.list {
  flex: 1;
  overflow: auto;
  padding: 8px;
  min-width: 0;
}
.body.split .list {
  flex: 0 0 42%;
  border-right: 1px solid var(--border);
}
.row {
  width: 100%;
  display: grid;
  grid-template-columns: 56px 1fr auto;
  gap: 8px;
  align-items: center;
  text-align: left;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.row:hover { background: var(--bg-muted); }
.row.on {
  background: var(--primary-soft);
  border-color: color-mix(in srgb, var(--primary) 28%, transparent);
}
.row.self { opacity: 0.72; }
.port {
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
}
.meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.process {
  font-size: 13px;
  color: var(--text-h);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}
.addr {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: var(--mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tag {
  font-size: 11px;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 1px 6px;
  flex-shrink: 0;
}
.actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
}
.row:hover .actions,
.row.on .actions { opacity: 1; }
.empty {
  margin: 24px 8px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}
.preview {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.preview-bar {
  font-size: 12px;
  color: var(--text-secondary);
}
.hint {
  font-size: 11px;
  opacity: 0.8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 42%;
}
.link {
  color: var(--primary);
  text-decoration: none;
  font-size: 12px;
}
.link:hover { text-decoration: underline; }
.frame {
  flex: 1;
  width: 100%;
  border: 0;
  background: #fff;
}
.icon-btn { width: 28px; height: 28px; }
.icon-btn.danger:hover {
  color: var(--error-text, #dc2626);
  background: color-mix(in srgb, #ef4444 12%, transparent);
}
</style>
