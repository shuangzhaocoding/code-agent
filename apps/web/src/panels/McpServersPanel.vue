<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'

type McpTool = { name: string; remote?: string; description?: string }
type McpServer = {
  name: string
  transport: string
  command?: string
  args?: string[]
  url?: string
  env?: Record<string, string>
  headers?: Record<string, string>
  enabled?: boolean
  origin?: string
  status?: string
  error?: string
  tools?: McpTool[]
}
type McpPreset = {
  id: string
  title: string
  transport: string
  command?: string
  args?: string[]
  url?: string
  hint?: string
}

const { t } = useI18n()
const store = useAppStore()
const servers = ref<McpServer[]>([])
const presets = ref<McpPreset[]>([])
const loading = ref(false)
const saving = ref(false)
const testing = ref('')
const error = ref('')
const formOpen = ref(false)
const editing = ref('')
const form = ref({
  name: '',
  transport: 'stdio',
  command: '',
  args: '',
  url: '',
  env: '',
  headers: '',
  enabled: true,
  origin: 'workspace',
})

const workspaceId = computed(() => store.workspaceId)

function qs() {
  return workspaceId.value ? `?workspace_id=${encodeURIComponent(workspaceId.value)}` : ''
}

function parsePairs(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || !trimmed.includes('=')) continue
    const i = trimmed.indexOf('=')
    out[trimmed.slice(0, i).trim()] = trimmed.slice(i + 1).trim()
  }
  return out
}

function formatPairs(record?: Record<string, string>) {
  return Object.entries(record || {})
    .map(([k, v]) => `${k}=${v}`)
    .join('\n')
}

function parseArgs(text: string): string[] {
  const raw = text.trim()
  if (!raw) return []
  if (raw.startsWith('[')) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) return parsed.map(String)
    } catch {
      /* fall through */
    }
  }
  return raw.split(/\s+/).filter(Boolean)
}

function payload() {
  return {
    name: form.value.name.trim(),
    transport: form.value.transport,
    command: form.value.command.trim(),
    args: parseArgs(form.value.args),
    url: form.value.url.trim(),
    env: parsePairs(form.value.env),
    headers: parsePairs(form.value.headers),
    enabled: form.value.enabled,
    origin: form.value.origin,
    workspace_id: workspaceId.value,
  }
}

function resetForm() {
  editing.value = ''
  form.value = {
    name: '',
    transport: 'stdio',
    command: '',
    args: '',
    url: '',
    env: '',
    headers: '',
    enabled: true,
    origin: workspaceId.value ? 'workspace' : 'user',
  }
}

function applyPreset(preset: McpPreset) {
  formOpen.value = true
  form.value = {
    name: form.value.name || preset.id,
    transport: preset.transport,
    command: preset.command || '',
    args: (preset.args || []).join(' '),
    url: preset.url || '',
    env: '',
    headers: '',
    enabled: true,
    origin: workspaceId.value ? 'workspace' : 'user',
  }
}

function editServer(item: McpServer) {
  editing.value = item.name
  formOpen.value = true
  form.value = {
    name: item.name,
    transport: item.transport || 'stdio',
    command: item.command || '',
    args: (item.args || []).join(' '),
    url: item.url || '',
    env: formatPairs(item.env),
    headers: formatPairs(item.headers),
    enabled: item.enabled !== false,
    origin: item.origin || 'workspace',
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [list, presetData] = await Promise.all([
      api<{ servers: McpServer[] }>(`/api/mcp/servers${qs()}`),
      presets.value.length ? Promise.resolve({ presets: presets.value }) : api<{ presets: McpPreset[] }>('/api/mcp/presets'),
    ])
    servers.value = list.servers || []
    if (presetData.presets?.length) presets.value = presetData.presets
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.name.trim() || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await api('/api/mcp/servers', { method: 'POST', body: JSON.stringify(payload()) })
    formOpen.value = false
    resetForm()
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    saving.value = false
  }
}

async function remove(item: McpServer) {
  error.value = ''
  try {
    await api(
      `/api/mcp/servers/${encodeURIComponent(item.name)}?${new URLSearchParams({
        ...(workspaceId.value ? { workspace_id: workspaceId.value } : {}),
        origin: item.origin || 'workspace',
      }).toString()}`,
      { method: 'DELETE' },
    )
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

async function testOne(item?: McpServer) {
  const body = item
    ? {
        ...item,
        workspace_id: workspaceId.value,
      }
    : payload()
  const key = String(body.name || '')
  testing.value = key
  error.value = ''
  try {
    const result = await api<{ ok: boolean; tools: unknown[]; error: string }>('/api/mcp/servers/test', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    if (!result.ok) error.value = result.error || t('plugins.mcp.testFailed')
    else if (item) await refreshTools()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    testing.value = ''
  }
}

async function refreshTools() {
  loading.value = true
  error.value = ''
  try {
    const data = await api<{ servers: McpServer[] }>(`/api/mcp/refresh${qs()}`, { method: 'POST' })
    servers.value = data.servers || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

function statusLabel(item: McpServer) {
  if (item.enabled === false) return t('common.disabled')
  if (item.status === 'ok') return t('plugins.mcp.connected')
  if (item.status === 'error') return t('plugins.mcp.error')
  return t('plugins.mcp.idle')
}

watch(workspaceId, () => void load())
onMounted(() => void load())
</script>

<template>
  <section class="mcp-panel">
    <header class="mcp-head">
      <div>
        <h2>{{ t('plugins.mcp.title') }}</h2>
        <p>{{ t('plugins.mcp.lead') }}</p>
      </div>
      <div class="mcp-actions">
        <button type="button" class="btn btn-ghost" :disabled="loading" @click="refreshTools">
          <AppIcon name="refresh" :size="15" />
          {{ t('plugins.mcp.refreshTools') }}
        </button>
        <button
          type="button"
          class="btn btn-ghost"
          @click="formOpen = !formOpen; if (formOpen && !editing) resetForm()"
        >
          <AppIcon name="plus" :size="15" />
          {{ t('plugins.mcp.add') }}
        </button>
      </div>
    </header>

    <p class="mcp-note">{{ t('plugins.mcp.noMarket') }}</p>

    <div class="preset-row">
      <button
        v-for="preset in presets"
        :key="preset.id"
        type="button"
        class="preset-chip"
        :title="preset.hint"
        @click="applyPreset(preset)"
      >
        {{ preset.title }}
      </button>
    </div>

    <p v-if="error" class="banner err">{{ error }}</p>

    <form v-if="formOpen" class="mcp-form" @submit.prevent="save">
      <div class="grid">
        <label>
          {{ t('plugins.mcp.name') }}
          <input v-model="form.name" required />
        </label>
        <label>
          {{ t('plugins.mcp.origin') }}
          <select v-model="form.origin">
            <option value="workspace" :disabled="!workspaceId">{{ t('plugins.originWorkspace') }}</option>
            <option value="user">{{ t('plugins.originUser') }}</option>
          </select>
        </label>
        <label>
          {{ t('plugins.mcp.transport') }}
          <select v-model="form.transport">
            <option value="stdio">stdio</option>
            <option value="http">http</option>
          </select>
        </label>
        <label class="check">
          <input v-model="form.enabled" type="checkbox" />
          {{ t('common.enabled') }}
        </label>
      </div>
      <div v-if="form.transport === 'stdio'" class="grid">
        <label>
          {{ t('plugins.mcp.command') }}
          <input v-model="form.command" placeholder="npx" />
        </label>
        <label class="wide">
          {{ t('plugins.mcp.args') }}
          <input v-model="form.args" placeholder="-y @playwright/mcp@latest" />
        </label>
      </div>
      <label v-else>
        {{ t('plugins.mcp.url') }}
        <input v-model="form.url" placeholder="https://mcp.figma.com/mcp" />
      </label>
      <div class="grid">
        <label>
          {{ t('plugins.mcp.env') }}
          <textarea v-model="form.env" rows="3" :placeholder="t('plugins.mcp.pairHint')" />
        </label>
        <label>
          {{ t('plugins.mcp.headers') }}
          <textarea v-model="form.headers" rows="3" placeholder="Authorization=Bearer …" />
        </label>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-ghost" :disabled="!!testing" @click="testOne()">
          {{ testing && !editing ? t('plugins.mcp.testing') : t('plugins.mcp.test') }}
        </button>
        <button type="submit" class="btn btn-primary" :disabled="saving">{{ t('common.save') }}</button>
        <button type="button" class="btn btn-ghost" @click="formOpen = false">{{ t('common.cancel') }}</button>
      </div>
    </form>

    <div v-if="!servers.length && !loading" class="empty">{{ t('plugins.mcp.empty') }}</div>
    <article v-for="item in servers" :key="`${item.origin}:${item.name}`" class="mcp-card" :class="{ off: item.enabled === false }">
      <div class="card-main">
        <strong>{{ item.name }}</strong>
        <span class="pill">{{ item.transport }}</span>
        <span class="pill origin">{{ item.origin === 'user' ? t('plugins.originUser') : t('plugins.originWorkspace') }}</span>
        <span class="status" :class="item.status">{{ statusLabel(item) }}</span>
      </div>
      <p class="meta">{{ item.command ? [item.command, ...(item.args || [])].join(' ') : item.url }}</p>
      <p v-if="item.error" class="err-line">{{ item.error }}</p>
      <p v-if="item.tools?.length" class="tools">
        {{ t('plugins.mcp.toolCount', { n: item.tools.length }) }}
        · {{ item.tools.map((tool) => tool.remote || tool.name).join(', ') }}
      </p>
      <div class="card-actions">
        <button type="button" class="btn btn-ghost" @click="editServer(item)">{{ t('common.edit') }}</button>
        <button type="button" class="btn btn-ghost" :disabled="testing === item.name" @click="testOne(item)">
          {{ testing === item.name ? t('plugins.mcp.testing') : t('plugins.mcp.test') }}
        </button>
        <button type="button" class="btn btn-ghost danger" @click="remove(item)">{{ t('common.delete') }}</button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.mcp-panel {
  margin-bottom: 22px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border);
}
.mcp-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.mcp-head h2 {
  margin: 0;
  font-size: 15px;
  color: var(--text-h);
}
.mcp-head p,
.mcp-note {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.mcp-note { margin: 8px 0 12px; }
.mcp-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.preset-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.preset-chip {
  height: 26px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-bg);
  color: var(--text-h);
  font-size: 12px;
  cursor: pointer;
}
.preset-chip:hover { border-color: color-mix(in srgb, #0891b2 45%, var(--border)); }
.banner.err, .err-line { color: var(--danger); font-size: 12.5px; }
.mcp-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
}
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
.mcp-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary); }
.mcp-form input, .mcp-form select, .mcp-form textarea {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text-h);
  padding: 6px 8px;
  font-size: 13px;
}
.mcp-form .wide { grid-column: 1 / -1; }
.check { flex-direction: row !important; align-items: center; gap: 8px; }
.form-actions { display: flex; gap: 8px; }
.empty { font-size: 13px; color: var(--text-muted); padding: 8px 0 4px; }
.mcp-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  margin-bottom: 8px;
  background: var(--panel-bg);
}
.mcp-card.off { opacity: 0.65; }
.card-main { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.pill, .status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--text-secondary);
}
.status.ok { color: #059669; border-color: color-mix(in srgb, #059669 35%, var(--border)); }
.status.error { color: var(--danger); }
.meta, .tools { margin: 6px 0 0; font-size: 12px; color: var(--text-muted); font-family: var(--mono); }
.card-actions { display: flex; gap: 6px; margin-top: 8px; }
.danger { color: var(--danger); }
</style>
