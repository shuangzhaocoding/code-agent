<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import { usePortsWatch, type PortItem } from '@/composables/usePortsWatch'

const { t } = useI18n()
const store = useAppStore()
const {
  ports: livePorts,
  highlightedPorts,
  error,
  loading,
  refresh: refreshShared,
  clearPortHighlighted,
} = usePortsWatch()
const killing = ref<number | null>(null)
const query = ref('')
const previewPort = ref<number | null>(null)
const listRef = ref<HTMLElement | null>(null)
/** When off, freeze the list in the panel; shared poller still runs for toast. */
const autoRefresh = ref(true)
const frozenPorts = ref<PortItem[] | null>(null)

const ports = computed(() => frozenPorts.value ?? livePorts.value)

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

watch(
  highlightedPorts,
  (set) => {
    if (!set.size) return
    const port = [...set].at(-1)
    if (port == null) return
    nextTick(() => {
      const el = listRef.value?.querySelector(`[data-port="${port}"]`)
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })
  },
  { deep: true },
)

watch(
  ports,
  (list) => {
    if (previewPort.value != null && !list.some((p) => p.port === previewPort.value)) {
      previewPort.value = null
    }
  },
  { deep: true },
)

async function refresh() {
  frozenPorts.value = null
  autoRefresh.value = true
  await refreshShared()
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
    error.value = t('ports.copyFail')
  }
}

function openPreview(item: PortItem) {
  if (item.self) return
  clearPortHighlighted(item.port)
  previewPort.value = item.port
}

function closePreview() {
  previewPort.value = null
}

async function killPort(item: PortItem) {
  if (item.self || !item.pid) return
  const ok = await store.askConfirm({
    title: t('ports.killTitle'),
    summary: t('ports.killSummary', { port: item.port, process: item.process || 'unknown', pid: item.pid }),
    details: item.cmdline || undefined,
    confirmLabel: t('ports.kill'),
    cancelLabel: t('common.cancel'),
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

function onToggleAuto() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) frozenPorts.value = null
  else frozenPorts.value = livePorts.value.map((p) => ({ ...p }))
}
</script>

<template>
  <div class="panel-shell ports panel-chromeless">
    <div class="ports-bar">
      <span class="title">
        <AppIcon name="ports" :size="14" />
        {{ t('ports.title') }}
        <span class="count">{{ filtered.length }}</span>
        <span v-if="highlightedPorts.size" class="new-count">{{ highlightedPorts.size }}</span>
      </span>
      <span class="spacer" />
      <label class="auto">
        <input type="checkbox" :checked="autoRefresh" @change="onToggleAuto" />
        {{ t('ports.autoRefresh') }}
      </label>
      <button type="button" class="icon-btn icon-btn-ghost" :title="t('common.refresh')" :disabled="loading" @click="refresh">
        <AppIcon name="refresh" :size="14" />
      </button>
    </div>

    <div class="search">
      <AppIcon name="search" :size="14" />
        <input v-model="query" type="search" :placeholder="t('ports.search')" />
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="body" :class="{ split: previewUrl }">
      <div ref="listRef" class="list">
        <button
          v-for="item in filtered"
          :key="`${item.address}:${item.port}`"
          type="button"
          class="row"
          :class="{
            on: previewPort === item.port,
            self: item.self,
            new: highlightedPorts.has(item.port),
          }"
          :data-port="item.port"
          @click="openPreview(item)"
          @dblclick="openExternal(item)"
        >
          <span class="port">
            {{ item.port }}
            <span v-if="highlightedPorts.has(item.port)" class="new-badge">{{ t('ports.newBadge') }}</span>
          </span>
          <span class="meta">
            <span class="process">
              {{ item.process || 'unknown' }}
              <span v-if="item.self" class="tag">{{ t('ports.self') }}</span>
            </span>
            <span class="addr">{{ item.address }} · {{ item.connect_host || '127.0.0.1' }} · pid {{ item.pid ?? '—' }}</span>
          </span>
          <span class="actions" @click.stop>
            <button type="button" class="icon-btn icon-btn-ghost" :title="t('ports.openProxy')" @click="openExternal(item)">
              <AppIcon name="globe" :size="13" />
            </button>
            <button type="button" class="icon-btn icon-btn-ghost" :title="t('ports.copyLocal', { url: item.url })" @click="copyUrl(item)">
              <AppIcon name="file" :size="13" />
            </button>
            <button
              type="button"
              class="icon-btn icon-btn-ghost"
              :title="t('ports.preview')"
              :disabled="item.self"
              @click="openPreview(item)"
            >
              <AppIcon name="eye" :size="13" />
            </button>
            <button
              type="button"
              class="icon-btn icon-btn-ghost danger"
              :title="t('ports.kill')"
              :disabled="item.self || !item.pid || killing === item.port"
              @click="killPort(item)"
            >
              <AppIcon name="trash" :size="13" />
            </button>
          </span>
        </button>
        <p v-if="!loading && !filtered.length" class="empty">{{ t('ports.empty') }}</p>
      </div>

      <div v-if="previewUrl" class="preview">
        <div class="preview-bar">
          <span>{{ t('ports.previewTitle', { port: previewPort }) }}</span>
          <span class="hint">{{ t('ports.previewHint') }}</span>
          <span class="spacer" />
          <a class="link" :href="previewUrl" target="_blank" rel="noopener">{{ t('ports.openTab') }}</a>
          <button type="button" class="icon-btn icon-btn-ghost" :title="t('ports.closePreview')" @click="closePreview">×</button>
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
.new-count {
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: var(--primary);
  border-radius: 999px;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
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
.row.new {
  border-color: color-mix(in srgb, var(--primary) 55%, transparent);
  background: color-mix(in srgb, var(--primary) 14%, var(--panel-bg));
  animation: port-new-pulse 1.4s ease-in-out 3;
}
.row.new.on {
  background: color-mix(in srgb, var(--primary) 22%, var(--panel-bg));
}
.row.self { opacity: 0.72; }
.port {
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.new-badge {
  font-family: var(--sans, system-ui);
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  color: #fff;
  background: var(--primary);
  border-radius: 999px;
  padding: 2px 6px;
  flex-shrink: 0;
}
@keyframes port-new-pulse {
  0%, 100% { box-shadow: inset 0 0 0 0 color-mix(in srgb, var(--primary) 0%, transparent); }
  50% { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 45%, transparent); }
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
