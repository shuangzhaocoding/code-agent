<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import AppIcon from '@/components/AppIcon.vue'
import type { LlmModel, LlmPreset, LlmProvider, ModelCapabilities, ModelParams, ProviderBalance } from '@/types/llm'

const store = useAppStore()
const error = ref('')
const busy = ref(false)
const showCustom = ref(false)
const testingId = ref<string | null>(null)
const probe = ref<{
  providerId: string
  total: number
  done: number
  ok: number
  fail: number
  current: string
  byId: Record<string, { ok: boolean; error?: string }>
} | null>(null)
const syncingId = ref<string | null>(null)
const editingProviderId = ref<string | null>(null)
const editingModelId = ref<string | null>(null)
const presets = ref<LlmPreset[]>([])
const balances = ref<Record<string, { loading: boolean; data?: ProviderBalance; error?: string }>>({})
const notices = ref<Record<string, { id: number; kind: 'ok' | 'fail' | 'info'; text: string }>>({})
const collapsedIds = ref<Record<string, boolean>>(loadCollapsed())
const modelQuery = ref<Record<string, string>>({})
const AUTO_COLLAPSE_AT = 8
const COLLAPSE_KEY = 'ca.models.collapsed'
let noticeSeq = 0
const noticeTimers: Record<string, number> = {}

function loadCollapsed(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem('ca.models.collapsed')
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function clearNotice(providerId: string, id?: number) {
  if (id != null && notices.value[providerId]?.id !== id) return
  window.clearTimeout(noticeTimers[providerId])
  delete noticeTimers[providerId]
  if (!notices.value[providerId]) return
  const next = { ...notices.value }
  delete next[providerId]
  notices.value = next
}

function setNotice(providerId: string, kind: 'ok' | 'fail' | 'info', text: string) {
  const id = ++noticeSeq
  window.clearTimeout(noticeTimers[providerId])
  notices.value = { ...notices.value, [providerId]: { id, kind, text } }
  noticeTimers[providerId] = window.setTimeout(() => clearNotice(providerId, id), 3000)
}

function isModelsCollapsed(p: LlmProvider) {
  if (Object.prototype.hasOwnProperty.call(collapsedIds.value, p.id)) return collapsedIds.value[p.id]
  return (p.models || []).length > AUTO_COLLAPSE_AT
}

function toggleModelsCollapsed(p: LlmProvider) {
  const next = { ...collapsedIds.value, [p.id]: !isModelsCollapsed(p) }
  collapsedIds.value = next
  localStorage.setItem(COLLAPSE_KEY, JSON.stringify(next))
}

function setModelQuery(providerId: string, value: string) {
  modelQuery.value = { ...modelQuery.value, [providerId]: value }
}

function visibleModels(p: LlmProvider) {
  const q = (modelQuery.value[p.id] || '').trim().toLowerCase()
  const models = p.models || []
  if (!q) return models
  return models.filter(
    (m) => m.display_name.toLowerCase().includes(q) || m.model_id.toLowerCase().includes(q),
  )
}

function modelStats(p: LlmProvider) {
  let ok = 0
  let fail = 0
  let unknown = 0
  for (const m of p.models || []) {
    const kind = availabilityLabel(m, p.id).kind
    if (kind === 'ok') ok += 1
    else if (kind === 'fail') fail += 1
    else unknown += 1
  }
  return { total: (p.models || []).length, ok, fail, unknown }
}

const presetMeta: Record<string, { desc: string; icon: string; accent: string }> = {
  deepseek: { desc: 'DeepSeek 官方 · thinking.budget_tokens', icon: 'think', accent: '#4f6bff' },
  qwen: { desc: '阿里云 DashScope · enable_thinking', icon: 'think', accent: '#f97316' },
  ollama: { desc: '本地模型服务', icon: 'chip', accent: '#059669' },
  openai: { desc: 'OpenAI 官方 · reasoning.effort', icon: 'globe', accent: '#0891b2' },
  aivalux: { desc: 'Codex 中转 · Responses API', icon: 'globe', accent: '#7c3aed' },
  gateway: { desc: 'OpenAI 兼容中转 · 按模型推断思考参数', icon: 'globe', accent: '#6366f1' },
  ccx: { desc: 'CCX 网关 · Chat + Responses 双入口', icon: 'globe', accent: '#0ea5e9' },
}

const form = reactive({
  name: 'DeepSeek',
  kind: 'deepseek',
  base_url: 'https://api.deepseek.com/v1',
  api_key: '',
})

const providerEdit = reactive({
  name: '',
  kind: '',
  base_url: '',
  api_key: '',
})

const modelEdit = reactive({
  display_name: '',
  model_id: '',
  context_window: 128000,
  supports_tools: true,
  supports_vision: false,
  supports_thinking: false,
  supports_audio: false,
  extraKey: '',
  extraCaps: [] as { key: string; label: string; supported: boolean }[],
  is_default: false,
  use_top_p: false,
  params: {} as ModelParams,
  capabilities: {} as ModelCapabilities,
})

const providers = computed(() => store.providers as LlmProvider[])

const presetCards = computed(() =>
  presets.value.map((preset) => ({
    ...preset,
    label: preset.title || preset.name,
    desc: presetMeta[preset.kind]?.desc || preset.base_url,
    icon: presetMeta[preset.kind]?.icon || 'chip',
    accent: presetMeta[preset.kind]?.accent || '#4f6bff',
  })),
)

onMounted(async () => {
  await Promise.all([store.loadProviders(), loadPresets()])
  await runPendingProbe()
})

onUnmounted(() => {
  for (const id of Object.keys(noticeTimers)) window.clearTimeout(noticeTimers[id])
})

watch(
  () => (store.providers as LlmProvider[]).filter((p) => p.supports_balance).map((p) => p.id).join('|'),
  (ids) => {
    if (ids) void loadBalances()
  },
)

watch(
  () => store.pendingModelProbe,
  (pending) => {
    if (pending) void runPendingProbe()
  },
)

async function runPendingProbe() {
  if (!store.pendingModelProbe) return
  store.pendingModelProbe = false
  for (const provider of store.providers) {
    await testProvider(provider.id)
  }
}

async function loadPresets() {
  try {
    presets.value = await api<LlmPreset[]>('/api/llm/presets')
  } catch {
    presets.value = []
  }
}

async function loadBalance(id: string, notify = false) {
  balances.value = { ...balances.value, [id]: { loading: true, data: balances.value[id]?.data, error: undefined } }
  try {
    const data = await api<ProviderBalance>(`/api/llm/providers/${id}/balance`)
    balances.value = { ...balances.value, [id]: { loading: false, data } }
    if (notify) setNotice(id, 'ok', `余额已刷新：${formatBalance(data)}`)
  } catch (err) {
    const text = err instanceof Error ? err.message : String(err)
    balances.value = {
      ...balances.value,
      [id]: { loading: false, error: text },
    }
    if (notify) setNotice(id, 'fail', `刷新余额失败：${text}`)
  }
}

async function loadBalances() {
  const ids = (store.providers as LlmProvider[]).filter((p) => p.supports_balance).map((p) => p.id)
  await Promise.all(ids.map((id) => loadBalance(id)))
}

function formatBalance(data: ProviderBalance) {
  const currency = data.currency || data.items?.[0]?.currency || ''
  const total = data.total || data.items?.[0]?.total || ''
  if (!total) return '—'
  if (currency === 'CNY') return `¥${total}`
  if (currency === 'USD') return `$${total}`
  return currency ? `${currency} ${total}` : total
}

function onKindChange() {
  const preset = presets.value.find((item) => item.kind === form.kind)
  if (preset) {
    form.name = preset.name
    form.base_url = preset.base_url
    return
  }
  if (form.kind === 'aivalux') {
    form.name = 'AIValux Codex'
    form.base_url = 'https://www.aivalux.com'
  } else if (form.kind === 'gateway') {
    form.name = 'API Gateway'
    form.base_url = 'https://api.example.com/v1'
  } else if (form.kind === 'ccx') {
    form.name = 'CCX'
    form.base_url = 'http://127.0.0.1:3000/v1'
  } else if (form.kind === 'openai_compat' || form.kind === 'custom') {
    form.name = 'OpenAI Compatible'
    form.base_url = 'https://api.openai.com/v1'
  }
}

async function applyPreset(kind: string) {
  error.value = ''
  busy.value = true
  try {
    await api(`/api/llm/presets/${kind}`, {
      method: 'POST',
      body: JSON.stringify({ api_key: form.api_key || undefined, make_default: true }),
    })
    form.api_key = ''
    await store.loadProviders()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

async function addCustom() {
  error.value = ''
  busy.value = true
  try {
    await api('/api/llm/providers', {
      method: 'POST',
      body: JSON.stringify({
        name: form.name,
        kind: form.kind,
        base_url: form.base_url,
        api_key: form.api_key,
        sync_models: true,
        make_default: true,
      }),
    })
    form.api_key = ''
    showCustom.value = false
    await store.loadProviders()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

function startEditProvider(p: LlmProvider) {
  editingProviderId.value = p.id
  providerEdit.name = p.name
  providerEdit.kind = p.kind
  providerEdit.base_url = p.base_url
  providerEdit.api_key = ''
}

function cancelEditProvider() {
  editingProviderId.value = null
}

async function saveProvider(id: string) {
  busy.value = true
  error.value = ''
  try {
    const body: Record<string, unknown> = {
      name: providerEdit.name,
      kind: providerEdit.kind,
      base_url: providerEdit.base_url,
    }
    if (providerEdit.api_key) body.api_key = providerEdit.api_key
    await api(`/api/llm/providers/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
    editingProviderId.value = null
    await store.loadProviders()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

async function removeProvider(p: LlmProvider) {
  const ok = await store.askConfirm({
    title: '删除 Provider',
    summary: `确定删除「${p.name}」及其所有模型？`,
    confirmLabel: '删除',
    danger: true,
  })
  if (!ok) return
  busy.value = true
  try {
    await api(`/api/llm/providers/${p.id}`, { method: 'DELETE' })
    await store.loadProviders()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

async function syncModels(id: string) {
  syncingId.value = id
  error.value = ''
  try {
    const res = await api<{ count: number }>(`/api/llm/providers/${id}/sync-models`, {
      method: 'POST',
      body: JSON.stringify({ make_default: false, disable_missing: true }),
    })
    const text = `已同步 ${res.count} 个模型，已保留此前检测的可用性`
    setNotice(id, 'ok', text)
    await store.loadProviders()
  } catch (err) {
    const text = err instanceof Error ? err.message : String(err)
    setNotice(id, 'fail', text)
  } finally {
    syncingId.value = null
  }
}

async function testProvider(id: string) {
  testingId.value = id
  error.value = ''
  probe.value = { providerId: id, total: 0, done: 0, ok: 0, fail: 0, current: '', byId: {} }
  try {
    const res = await fetch(`/api/llm/providers/${id}/test`, { method: 'POST' })
    if (!res.ok || !res.body) {
      const raw = await res.text()
      throw new Error(raw || res.statusText)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (!line.trim()) continue
        const ev = JSON.parse(line) as Record<string, unknown>
        const state: NonNullable<typeof probe.value> = probe.value
        if (!state) continue
        if (ev.type === 'start') {
          probe.value = { ...state, total: Number(ev.total || 0) }
        } else if (ev.type === 'item') {
          const mid = String(ev.id || '')
          const byId = { ...state.byId }
          if (mid) byId[mid] = { ok: Boolean(ev.ok), error: String(ev.error || '') }
          probe.value = {
            ...state,
            done: Number(ev.done || 0),
            total: Number(ev.total || state.total),
            ok: Number(ev.ok_count || 0),
            fail: Number(ev.fail_count || 0),
            current: String(ev.display_name || ev.model_id || ''),
            byId,
          }
        } else if (ev.type === 'done') {
          const ok = Number(ev.ok_count || 0)
          const fail = Number(ev.fail_count || 0)
          const total = Number(ev.total || state.total)
          probe.value = { ...state, ok, fail, done: total, total }
          const text = `已检测：${ok} 个可用 / ${fail} 个不可用`
          setNotice(id, fail ? 'info' : 'ok', text)
        } else if (ev.type === 'error') {
          throw new Error(String(ev.message || '探测失败'))
        }
      }
    }
    await store.loadProviders()
  } catch (err) {
    const text = err instanceof Error ? err.message : String(err)
    setNotice(id, 'fail', text)
  } finally {
    testingId.value = null
    probe.value = null
  }
}

function availabilityLabel(m: LlmModel, providerId?: string) {
  const p = probe.value
  const live = p && p.providerId === providerId ? p.byId[m.id] : undefined
  if (p && p.providerId === providerId && !live) {
    return { text: '检测中', kind: 'checking', title: '正在探测…' }
  }
  if (live) {
    return live.ok
      ? { text: '可用', kind: 'ok', title: '探测成功' }
      : { text: '不可用', kind: 'fail', title: live.error || '探测失败' }
  }
  const avail = m.availability
  if (!avail || avail.ok == null) return { text: '未检测', kind: 'unknown', title: '点击测试连接以检测可用性' }
  if (avail.ok) {
    const ms = avail.latency_ms ? ` · ${avail.latency_ms}ms` : ''
    return { text: '可用', kind: 'ok', title: `探测成功${ms}` }
  }
  return { text: '不可用', kind: 'fail', title: avail.error || '探测失败' }
}

function probePercent(providerId: string) {
  const state = probe.value
  if (!state || state.providerId !== providerId || !state.total) return 0
  return Math.round((state.done / state.total) * 100)
}

function startEditModel(m: LlmModel) {
  editingModelId.value = m.id
  modelEdit.display_name = m.display_name
  modelEdit.model_id = m.model_id
  modelEdit.context_window = m.context_window || 128000
  modelEdit.supports_tools = m.supports_tools !== false
  modelEdit.supports_vision = Boolean(m.supports_vision || m.capabilities?.vision?.supported)
  modelEdit.supports_thinking = Boolean(m.capabilities?.thinking?.supported)
  modelEdit.supports_audio = Boolean(m.capabilities?.audio?.supported)
  modelEdit.extraKey = ''
  modelEdit.extraCaps = extraCapsFrom(m.capabilities)
  modelEdit.is_default = !!m.is_default
  modelEdit.capabilities = m.capabilities || {}
  modelEdit.params = { ...(m.params || {}) }
  modelEdit.use_top_p = m.params?.top_p != null && m.params.top_p < 1
}

function extraCapsFrom(caps?: ModelCapabilities) {
  const known = new Set(['temperature', 'max_tokens', 'top_p', 'thinking', 'tools', 'vision', 'audio', 'context_window', 'origin', 'overrides', 'availability', 'modalities', 'levels'])
  const out: { key: string; label: string; supported: boolean }[] = []
  for (const [key, value] of Object.entries(caps || {})) {
    if (known.has(key)) continue
    if (value && typeof value === 'object' && 'supported' in (value as object)) {
      out.push({ key, label: key, supported: Boolean((value as { supported?: boolean }).supported) })
    }
  }
  return out
}

function addExtraCap() {
  const key = modelEdit.extraKey.trim()
  if (!key || modelEdit.extraCaps.some((item) => item.key === key)) return
  modelEdit.extraCaps.push({ key, label: key, supported: true })
  modelEdit.extraKey = ''
}

function cancelEditModel() {
  editingModelId.value = null
}

function paramValue(key: keyof ModelParams) {
  const spec = modelEdit.capabilities[key]
  if (modelEdit.params[key] !== undefined) return modelEdit.params[key]
  return spec?.default
}

function setParamValue(key: keyof ModelParams, value: number) {
  modelEdit.params[key] = value
}

async function saveModel(id: string) {
  busy.value = true
  error.value = ''
  try {
    await api(`/api/llm/models/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        display_name: modelEdit.display_name,
        model_id: modelEdit.model_id,
        context_window: modelEdit.context_window,
        supports_tools: modelEdit.supports_tools,
        supports_vision: modelEdit.supports_vision,
        is_default: modelEdit.is_default,
        params: (() => {
          const params = { ...modelEdit.params }
          if (!modelEdit.use_top_p) delete params.top_p
          return params
        })(),
        capabilities: {
          ...modelEdit.capabilities,
          tools: { ...(modelEdit.capabilities.tools || {}), supported: modelEdit.supports_tools },
          vision: { ...(modelEdit.capabilities.vision || {}), supported: modelEdit.supports_vision },
          thinking: {
            ...(modelEdit.capabilities.thinking || {}),
            supported: modelEdit.supports_thinking,
            levels: modelEdit.supports_thinking
              ? modelEdit.capabilities.thinking?.levels || ['off', 'low', 'medium', 'high']
              : [],
          },
          audio: { ...(modelEdit.capabilities.audio || {}), supported: modelEdit.supports_audio },
          ...Object.fromEntries(modelEdit.extraCaps.map((item) => [item.key, { supported: item.supported }])),
        },
      }),
    })
    editingModelId.value = null
    await store.loadProviders()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

async function setDefaultModel(m: LlmModel) {
  if (m.is_default) return
  busy.value = true
  try {
    await api(`/api/llm/models/${m.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_default: true }),
    })
    await store.loadProviders()
  } finally {
    busy.value = false
  }
}

async function removeModel(m: LlmModel, providerName: string) {
  const ok = await store.askConfirm({
    title: '删除模型',
    summary: `确定删除「${providerName} / ${m.display_name}」？`,
    confirmLabel: '删除',
    danger: true,
  })
  if (!ok) return
  busy.value = true
  try {
    await api(`/api/llm/models/${m.id}`, { method: 'DELETE' })
    await store.loadProviders()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

function kindLabel(kind: string) {
  const map: Record<string, string> = {
    deepseek: 'DeepSeek',
    ollama: 'Ollama',
    openai: 'OpenAI',
    gateway: '中转站',
    ccx: 'CCX',
    aivalux: 'AIValux Codex',
    openai_compat: 'OpenAI 兼容',
    custom: 'Custom',
  }
  return map[kind] || kind
}

function capabilityTags(m: LlmModel) {
  const caps = m.capabilities || {}
  const tags: string[] = []
  if (caps.thinking?.supported) tags.push('思考')
  if (caps.tools?.supported ?? m.supports_tools) tags.push('工具')
  if (caps.vision?.supported ?? m.supports_vision) tags.push('视觉')
  if (caps.audio?.supported) tags.push('语音')
  if (caps.temperature?.supported) tags.push('温度')
  for (const [key, value] of Object.entries(caps)) {
    if (['temperature', 'max_tokens', 'top_p', 'thinking', 'tools', 'vision', 'audio', 'context_window', 'origin', 'overrides', 'availability', 'modalities'].includes(key)) continue
    if (value && typeof value === 'object' && (value as { supported?: boolean }).supported) tags.push(key)
  }
  return tags
}
</script>

<template>
  <div class="panel-shell models-panel">
    <div class="panel-body">
      <header class="page-head">
        <div>
          <h1 class="page-title">模型配置</h1>
          <p class="page-lead">从 Provider 接口自动获取模型列表，支持官方 API 与中转站。</p>
        </div>
      </header>

      <section class="section">
        <h2 class="section-title">快速添加</h2>
        <div class="preset-grid">
          <button
            v-for="preset in presetCards"
            :key="preset.kind"
            type="button"
            class="preset-card"
            :disabled="busy"
            @click="applyPreset(preset.kind)"
          >
            <span class="preset-icon" :style="{ '--accent': preset.accent }">
              <AppIcon :name="preset.icon" :size="20" />
            </span>
            <span class="preset-copy">
              <strong>{{ preset.label }}</strong>
              <span>{{ preset.desc }}</span>
            </span>
            <AppIcon class="preset-arrow" name="chevron-right" :size="16" />
          </button>
        </div>
        <label class="api-key-field">
          <span>API Key（需要 Key 的预设必填，添加后自动拉取模型列表）</span>
          <input v-model="form.api_key" class="field-control" type="password" placeholder="sk-…（Ollama 可留空）" />
        </label>
      </section>

      <section class="section">
        <div class="section-head">
          <h2 class="section-title">已配置</h2>
          <button type="button" class="btn btn-ghost" @click="showCustom = !showCustom">
            <AppIcon name="plus" :size="16" />
            {{ showCustom ? '收起自定义' : '自定义添加' }}
          </button>
      </div>

        <form v-if="showCustom" class="custom-form" @submit.prevent="addCustom">
          <div class="form-grid">
            <label>
              <span>名称</span>
              <input v-model="form.name" class="field-control" placeholder="Provider 名称" />
            </label>
            <label>
              <span>类型</span>
        <select v-model="form.kind" class="field-control" @change="onKindChange">
          <option value="deepseek">DeepSeek</option>
                <option value="aivalux">AIValux Codex</option>
                <option value="ccx">CCX</option>
                <option value="gateway">中转站</option>
          <option value="openai_compat">OpenAI Compatible</option>
          <option value="openai">OpenAI</option>
          <option value="ollama">Ollama</option>
          <option value="custom">Custom</option>
        </select>
            </label>
            <label class="span-2">
              <span>Base URL</span>
              <input v-model="form.base_url" class="field-control" placeholder="https://www.aivalux.com 或 https://www.aivalux.com/v1" />
            </label>
            <label class="span-2">
              <span>API Key</span>
              <input v-model="form.api_key" class="field-control" type="password" placeholder="可选（Ollama 可填 ollama）" />
            </label>
          </div>
          <p class="form-hint">Base URL 填网站地址即可（如 https://www.aivalux.com），系统会自动补全 /v1 并拉取模型。</p>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary" :disabled="busy">添加并同步模型</button>
          </div>
      </form>

        <p v-if="!providers.length" class="empty-note">暂无配置，使用上方快速添加或自定义接入。</p>

        <article v-for="p in providers" :key="p.id" class="provider-card">
          <template v-if="editingProviderId === p.id">
            <div class="form-grid">
              <label>
                <span>名称</span>
                <input v-model="providerEdit.name" class="field-control" />
              </label>
              <label>
                <span>类型</span>
                <input v-model="providerEdit.kind" class="field-control" />
              </label>
              <label class="span-2">
                <span>Base URL</span>
                <input v-model="providerEdit.base_url" class="field-control" />
              </label>
              <label class="span-2">
                <span>新 API Key（留空则不修改）</span>
                <input v-model="providerEdit.api_key" class="field-control" type="password" placeholder="留空保持不变" />
              </label>
            </div>
            <div class="card-actions">
              <button type="button" class="btn btn-primary" :disabled="busy" @click="saveProvider(p.id)">保存</button>
              <button type="button" class="btn" @click="cancelEditProvider">取消</button>
            </div>
          </template>

          <template v-else>
            <div class="provider-head">
              <div class="provider-title">
                <span class="provider-icon"><AppIcon name="chip" :size="18" /></span>
                <div>
                  <strong>{{ p.name }}</strong>
                  <span class="kind-badge">{{ kindLabel(p.kind) }}</span>
                </div>
              </div>
              <div class="card-actions inline">
                <button
                  type="button"
                  class="icon-btn icon-btn-ghost"
                  title="同步模型"
                  :disabled="syncingId === p.id"
                  @click="syncModels(p.id)"
                >
                  <AppIcon name="refresh" :size="16" />
                </button>
                <button
                  type="button"
                  class="icon-btn icon-btn-ghost"
                  :class="{ testing: testingId === p.id }"
                  title="测试连接"
                  :disabled="testingId === p.id"
                  @click="testProvider(p.id)"
                >
                  <AppIcon name="zap" :size="16" />
                </button>
                <button type="button" class="icon-btn icon-btn-ghost" title="编辑" @click="startEditProvider(p)">
                  <AppIcon name="pencil" :size="16" />
                </button>
                <button type="button" class="icon-btn icon-btn-ghost danger" title="删除" @click="removeProvider(p)">
                  <AppIcon name="trash" :size="16" />
                </button>
              </div>
            </div>
            <p class="provider-meta">{{ p.base_url }} · {{ p.api_key_masked || '无 Key' }} · {{ (p.models || []).length }} 个模型</p>
            <div v-if="p.supports_balance" class="provider-balance">
              <span class="balance-label">余额</span>
              <span v-if="balances[p.id]?.loading && !balances[p.id]?.data" class="balance-muted">查询中…</span>
              <span v-else-if="balances[p.id]?.error" class="balance-error" :title="balances[p.id]?.error">{{ balances[p.id]?.error }}</span>
              <template v-else-if="balances[p.id]?.data">
                <strong>{{ formatBalance(balances[p.id]!.data!) }}</strong>
                <span v-if="balances[p.id]!.data!.granted" class="balance-muted">赠送 {{ balances[p.id]!.data!.granted }}</span>
                <span v-if="balances[p.id]!.data!.available === false" class="balance-error">不可用</span>
              </template>
              <button
                type="button"
                class="icon-btn icon-btn-ghost"
                title="刷新余额"
                :disabled="balances[p.id]?.loading"
                @click="loadBalance(p.id, true)"
              >
                <AppIcon name="refresh" :size="16" :stroke-width="1.75" />
              </button>
            </div>
            <div v-if="notices[p.id]" class="provider-notice" :class="notices[p.id].kind">
              <span>{{ notices[p.id].text }}</span>
              <button type="button" class="notice-close" title="关闭" @click="clearNotice(p.id)">
                <AppIcon name="close" :size="16" :stroke-width="1.75" />
              </button>
            </div>
            <div v-if="probe?.providerId === p.id" class="probe-progress">
              <div class="probe-bar"><i :style="{ width: probePercent(p.id) + '%' }" /></div>
              <p class="probe-label">
                {{ probe.current ? `正在检测 ${probe.current}` : '准备检测' }}
                · {{ probe.done }}/{{ probe.total }}
                · 可用 {{ probe.ok }}
                · 失败 {{ probe.fail }}
              </p>
            </div>
            <button type="button" class="models-toggle" @click="toggleModelsCollapsed(p)">
              <AppIcon class="models-twist" name="chevron-right" :size="16" :stroke-width="1.75" :class="{ open: !isModelsCollapsed(p) }" />
              <span>模型 {{ modelStats(p).total }}</span>
              <span class="models-toggle-meta">
                可用 {{ modelStats(p).ok }}
                · 不可用 {{ modelStats(p).fail }}
                · 未检测 {{ modelStats(p).unknown }}
              </span>
            </button>
            <div v-if="!isModelsCollapsed(p)" class="model-list-wrap">
              <input
                v-if="(p.models || []).length > 12"
                class="model-filter"
                :value="modelQuery[p.id] || ''"
                placeholder="筛选模型名称或 ID"
                @input="setModelQuery(p.id, ($event.target as HTMLInputElement).value)"
              />
            <ul class="model-list">
              <li v-for="m in visibleModels(p)" :key="m.id" class="model-row">
                <template v-if="editingModelId === m.id">
                  <div class="model-edit-grid">
                    <input v-model="modelEdit.display_name" class="field-control" placeholder="显示名称" />
                    <input v-model="modelEdit.model_id" class="field-control" placeholder="model id" readonly />
                    <input v-model.number="modelEdit.context_window" class="field-control" type="number" placeholder="上下文" />
                    <label class="check-label">
                      <input v-model="modelEdit.supports_tools" type="checkbox" />
                      工具
                    </label>
                    <label class="check-label">
                      <input v-model="modelEdit.supports_vision" type="checkbox" />
                      视觉
                    </label>
                    <label class="check-label">
                      <input v-model="modelEdit.supports_thinking" type="checkbox" />
                      思考
                    </label>
                    <label class="check-label">
                      <input v-model="modelEdit.supports_audio" type="checkbox" />
                      语音
                    </label>
                    <label class="check-label">
                      <input v-model="modelEdit.is_default" type="checkbox" />
                      设为默认
                    </label>
                    <div class="span-2 extra-cap">
                      <input v-model="modelEdit.extraKey" class="field-control" placeholder="新增能力标识，如 web-search" />
                      <button type="button" class="btn btn-sm" @click="addExtraCap">添加能力</button>
                    </div>
                    <label v-for="item in modelEdit.extraCaps" :key="item.key" class="check-label">
                      <input v-model="item.supported" type="checkbox" />
                      {{ item.label }}
                    </label>
                    <template v-if="modelEdit.capabilities.temperature?.supported">
                      <label class="span-2 param-field">
                        <span>温度 ({{ paramValue('temperature') }})</span>
                        <input
                          type="range"
                          :min="modelEdit.capabilities.temperature.min ?? 0"
                          :max="modelEdit.capabilities.temperature.max ?? 2"
                          :step="modelEdit.capabilities.temperature.step ?? 0.1"
                          :value="paramValue('temperature')"
                          @input="setParamValue('temperature', Number(($event.target as HTMLInputElement).value))"
                        />
                      </label>
                    </template>
                    <template v-if="modelEdit.capabilities.max_tokens?.supported">
                      <label class="param-field">
                        <span>最大 Token</span>
                        <input
                          type="number"
                          class="field-control"
                          :min="modelEdit.capabilities.max_tokens.min ?? 1"
                          :max="modelEdit.capabilities.max_tokens.max ?? 128000"
                          :value="paramValue('max_tokens')"
                          @input="setParamValue('max_tokens', Number(($event.target as HTMLInputElement).value))"
                        />
                      </label>
                    </template>
                    <template v-if="modelEdit.capabilities.top_p?.supported">
                      <label class="check-label">
                        <input v-model="modelEdit.use_top_p" type="checkbox" />
                        传递 Top P
                      </label>
                      <label v-if="modelEdit.use_top_p" class="param-field">
                        <span>Top P ({{ paramValue('top_p') }})</span>
                        <input
                          type="range"
                          :min="modelEdit.capabilities.top_p.min ?? 0.05"
                          :max="0.99"
                          :step="modelEdit.capabilities.top_p.step ?? 0.05"
                          :value="paramValue('top_p')"
                          @input="setParamValue('top_p', Number(($event.target as HTMLInputElement).value))"
                        />
                      </label>
                    </template>
                  </div>
                  <div class="model-edit-actions">
                    <button type="button" class="btn btn-primary btn-sm" @click="saveModel(m.id)">保存</button>
                    <button type="button" class="btn btn-sm" @click="cancelEditModel">取消</button>
                  </div>
                </template>
                <template v-else>
                  <button
                    type="button"
                    class="model-name"
                    :class="{ default: m.is_default }"
                    @click="setDefaultModel(m)"
                  >
              {{ m.display_name }}
                    <span v-if="m.is_default" class="default-badge">默认</span>
                  </button>
                  <span
                    class="avail-badge"
                    :class="availabilityLabel(m, p.id).kind"
                    :title="availabilityLabel(m, p.id).title"
                  >{{ availabilityLabel(m, p.id).text }}</span>
                  <code class="model-id">{{ m.model_id }}</code>
                  <div class="cap-tags">
                    <span v-for="tag in capabilityTags(m)" :key="tag" class="cap-tag">{{ tag }}</span>
                  </div>
                  <div class="model-actions">
                    <button type="button" class="icon-btn icon-btn-ghost" title="编辑" @click="startEditModel(m)">
                      <AppIcon name="pencil" :size="16" :stroke-width="1.75" />
                    </button>
                    <button type="button" class="icon-btn icon-btn-ghost danger" title="删除" @click="removeModel(m, p.name)">
                      <AppIcon name="trash" :size="16" :stroke-width="1.75" />
                    </button>
                  </div>
                </template>
            </li>
          </ul>
              <p v-if="!(visibleModels(p).length)" class="model-empty">没有匹配的模型</p>
            </div>
          </template>
        </article>
      </section>
    </div>
  </div>
</template>

<style scoped>
.models-panel .panel-body {
  padding: 16px 20px 24px;
  overflow: auto;
  font-size: 12px;
}
.page-head { margin-bottom: 16px; }
.page-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-h);
}
.page-lead {
  margin: 0;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
}
.section { margin-bottom: 20px; }
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.section-title {
  margin: 0 0 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.section-head .section-title { margin-bottom: 0; }
.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}
.preset-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.preset-card:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  background: var(--primary-soft);
}
.preset-card:disabled { opacity: 0.6; cursor: wait; }
.preset-icon {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: color-mix(in srgb, var(--accent) 14%, var(--code-bg));
  color: var(--accent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 18%, transparent);
}
.preset-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.preset-copy strong {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}
.preset-copy span {
  font-size: 11px;
  color: var(--text-muted);
}
.preset-arrow { color: var(--text-muted); flex-shrink: 0; }
.api-key-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  max-width: 440px;
  font-size: 11px;
  color: var(--text-secondary);
}
.custom-form,
.provider-card {
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  padding: 12px 14px;
  margin-bottom: 10px;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.form-grid .span-2 { grid-column: span 2; }
.form-grid label,
.api-key-field,
.param-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}
.form-hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--text-muted);
}
.models-panel :deep(.field-control) {
  font-size: 12px;
  padding: 6px 9px;
  min-height: 30px;
}
.form-actions,
.card-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.card-actions.inline { margin-top: 0; }
.models-panel .btn {
  height: 30px;
  padding: 0 12px;
  font-size: 12px;
}
.empty-note {
  margin: 0;
  padding: 18px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  border: var(--border-width) dashed var(--border);
  border-radius: var(--radius-md);
}
.provider-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.provider-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.provider-title strong {
  font-size: 13px;
  color: var(--text-h);
  margin-right: 6px;
}
.provider-icon {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--primary-soft);
  color: var(--primary);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 16%, transparent);
}
.kind-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--code-bg);
  color: var(--text-muted);
}
.provider-meta {
  margin: 6px 0 10px;
  font-size: 11px;
  font-family: var(--mono);
  color: var(--text-muted);
}
.provider-balance {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: -4px 0 10px;
  min-height: 28px;
  font-size: 12px;
  color: var(--text);
}
.balance-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
}
.provider-balance strong {
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
}
.balance-muted {
  font-size: 11px;
  color: var(--text-muted);
}
.balance-error {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--danger);
}
.model-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: var(--border-width) solid var(--border);
}
.model-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: var(--border-width) solid var(--border);
  flex-wrap: wrap;
}
.model-row:last-child { border-bottom: 0; padding-bottom: 0; }
.model-name {
  border: 0;
  background: transparent;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0;
}
.model-name:hover { color: var(--primary); }
.default-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
}
.model-id {
  flex: 1;
  min-width: 120px;
  font-size: 10px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cap-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
@media (hover: hover) {
  .model-id,
  .cap-tags {
    display: none;
  }
  .model-row:hover .model-id,
  .model-row:focus-within .model-id {
    display: block;
  }
  .model-row:hover .cap-tags,
  .model-row:focus-within .cap-tags {
    display: flex;
  }
}
.cap-tag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--code-bg);
  color: var(--text-muted);
}
.avail-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--code-bg);
  color: var(--text-muted);
  white-space: nowrap;
}
.avail-badge.ok {
  color: #15803d;
  background: color-mix(in srgb, #22c55e 16%, var(--panel-bg));
}
.avail-badge.fail {
  color: #b91c1c;
  background: color-mix(in srgb, #ef4444 14%, var(--panel-bg));
}
.avail-badge.checking {
  color: var(--primary);
  background: var(--primary-soft);
  animation: avail-blink 0.9s ease-in-out infinite;
}
@keyframes avail-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}
.model-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.model-row:hover .model-actions { opacity: 1; }
.model-row:focus-within .model-actions { opacity: 1; }
.model-edit-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  width: 100%;
}
.span-2,
.extra-cap {
  grid-column: span 2;
}
.extra-cap {
  display: flex;
  gap: 8px;
  align-items: center;
}
.check-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-secondary);
}
.model-edit-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.icon-btn.testing {
  color: var(--primary);
  background: transparent;
  opacity: 1;
  pointer-events: none;
}
.icon-btn.testing :deep(svg) {
  animation: zap-pulse 0.7s ease-in-out infinite;
}
@keyframes zap-pulse {
  0%, 100% { transform: scale(1) rotate(0deg); opacity: 1; }
  40% { transform: scale(1.18) rotate(-12deg); opacity: 0.7; }
  70% { transform: scale(0.92) rotate(8deg); opacity: 1; }
}
.probe-progress {
  margin: 0 0 8px;
}
.probe-bar {
  height: 4px;
  border-radius: 999px;
  overflow: hidden;
  background: color-mix(in srgb, var(--primary) 16%, var(--code-bg));
}
.probe-bar i {
  display: block;
  height: 100%;
  width: 0;
  border-radius: inherit;
  background: var(--primary);
  transition: width 0.25s ease;
}
.probe-label {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--text-muted);
}
.btn-sm {
  height: 26px;
  padding: 0 9px;
  font-size: 11px;
}
.status-msg {
  margin: 0;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--error-text);
  background: color-mix(in srgb, var(--error-text) 10%, var(--panel-bg));
  border: var(--border-width) solid color-mix(in srgb, var(--error-text) 20%, var(--border));
}
.status-msg.ok {
  color: var(--primary);
  background: var(--primary-soft);
  border-color: color-mix(in srgb, var(--primary) 25%, var(--border));
}
.provider-notice {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0 0 8px;
  padding: 7px 8px 7px 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 1.4;
  border: var(--border-width) solid var(--border);
}
.provider-notice span {
  flex: 1;
  min-width: 0;
}
.notice-close {
  width: 20px;
  height: 20px;
  margin-top: -1px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  opacity: 0.65;
  cursor: pointer;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.notice-close:hover {
  opacity: 1;
  background: color-mix(in srgb, currentColor 12%, transparent);
}
.provider-notice.ok {
  color: #15803d;
  background: color-mix(in srgb, #22c55e 12%, var(--panel-bg));
  border-color: color-mix(in srgb, #22c55e 28%, var(--border));
}
.provider-notice.fail {
  color: var(--error-text, #b91c1c);
  background: color-mix(in srgb, #ef4444 10%, var(--panel-bg));
  border-color: color-mix(in srgb, #ef4444 22%, var(--border));
}
.provider-notice.info {
  color: var(--text-h);
  background: var(--primary-soft);
  border-color: color-mix(in srgb, var(--primary) 22%, var(--border));
}
.models-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0 0;
  padding: 8px 0 6px;
  border: 0;
  border-top: var(--border-width) solid var(--border);
  background: transparent;
  color: var(--text-h);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  text-align: left;
}
.models-toggle:hover { color: var(--primary); }
.models-twist {
  flex-shrink: 0;
  color: var(--text-muted);
  transition: transform 0.15s ease;
}
.models-twist.open { transform: rotate(90deg); }
.models-toggle-meta {
  margin-left: auto;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
}
.model-list-wrap { padding-top: 4px; }
.model-filter {
  width: 100%;
  margin: 0 0 8px;
  padding: 6px 9px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text);
  font-size: 12px;
}
.model-empty {
  margin: 0;
  padding: 10px 0 4px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
