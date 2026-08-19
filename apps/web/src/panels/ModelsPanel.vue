<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import AppIcon from '@/components/AppIcon.vue'

type Provider = {
  id: string
  name: string
  kind: string
  base_url: string
  api_key_masked?: string
  enabled?: boolean
  models?: Model[]
}

type Model = {
  id: string
  model_id: string
  display_name: string
  is_default?: boolean
  supports_tools?: boolean
  context_window?: number
}

const store = useAppStore()
const error = ref('')
const busy = ref(false)
const showCustom = ref(false)
const testingId = ref<string | null>(null)
const editingProviderId = ref<string | null>(null)
const editingModelId = ref<string | null>(null)

const presets = [
  { kind: 'deepseek', label: 'DeepSeek', desc: '官方 OpenAI 兼容接口', icon: 'sparkles', accent: '#4f6bff' },
  { kind: 'ollama', label: 'Ollama', desc: '本地模型服务', icon: 'chip', accent: '#059669' },
  { kind: 'openai', label: 'OpenAI', desc: 'GPT 系列模型', icon: 'globe', accent: '#0891b2' },
]

const form = reactive({
  name: 'DeepSeek',
  kind: 'deepseek',
  base_url: 'https://api.deepseek.com/v1',
  api_key: '',
  model_id: 'deepseek-chat',
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
  is_default: false,
})

const providers = computed(() => store.providers as Provider[])

onMounted(() => store.loadProviders())

function onKindChange() {
  if (form.kind === 'deepseek') {
    form.name = 'DeepSeek'
    form.base_url = 'https://api.deepseek.com/v1'
    form.model_id = 'deepseek-chat'
  } else if (form.kind === 'ollama') {
    form.name = 'Ollama'
    form.base_url = 'http://127.0.0.1:11434/v1'
    form.model_id = 'llama3.1'
    form.api_key = form.api_key || 'ollama'
  } else if (form.kind === 'openai') {
    form.name = 'OpenAI'
    form.base_url = 'https://api.openai.com/v1'
    form.model_id = 'gpt-4o-mini'
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
    const provider = await api<{ id: string }>('/api/llm/providers', {
      method: 'POST',
      body: JSON.stringify({
        name: form.name,
        kind: form.kind,
        base_url: form.base_url,
        api_key: form.api_key,
      }),
    })
    const extra =
      form.kind === 'deepseek' && form.model_id === 'deepseek-chat'
        ? [{ model_id: 'deepseek-reasoner', display_name: 'DeepSeek Reasoner', is_default: false }]
        : []
    await api('/api/llm/models', {
      method: 'POST',
      body: JSON.stringify({
        provider_id: provider.id,
        model_id: form.model_id,
        display_name: form.kind === 'deepseek' ? 'DeepSeek Chat' : form.model_id,
        is_default: true,
        supports_tools: true,
      }),
    })
    for (const m of extra) {
      await api('/api/llm/models', {
        method: 'POST',
        body: JSON.stringify({ provider_id: provider.id, supports_tools: true, ...m }),
      })
    }
    form.api_key = ''
    showCustom.value = false
    await store.loadProviders()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

function startEditProvider(p: Provider) {
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

async function removeProvider(p: Provider) {
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

async function testProvider(id: string) {
  testingId.value = id
  error.value = ''
  try {
    const res = await api<{ ok: boolean; reply: string }>(`/api/llm/providers/${id}/test`, { method: 'POST' })
    error.value = `连接成功：${res.reply?.slice(0, 80) || 'pong'}`
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    testingId.value = null
  }
}

function startEditModel(m: Model) {
  editingModelId.value = m.id
  modelEdit.display_name = m.display_name
  modelEdit.model_id = m.model_id
  modelEdit.context_window = m.context_window || 128000
  modelEdit.supports_tools = m.supports_tools !== false
  modelEdit.is_default = !!m.is_default
}

function cancelEditModel() {
  editingModelId.value = null
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
        is_default: modelEdit.is_default,
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

async function setDefaultModel(m: Model) {
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

async function removeModel(m: Model, providerName: string) {
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
    openai_compat: 'OpenAI 兼容',
    custom: 'Custom',
  }
  return map[kind] || kind
}
</script>

<template>
  <div class="panel-shell models-panel">
    <div class="panel-body">
      <header class="page-head">
        <div>
          <h1 class="page-title">模型配置</h1>
          <p class="page-lead">管理 LLM Provider 与可用模型，支持快速预设与自定义接入。</p>
        </div>
      </header>

      <section class="section">
        <h2 class="section-title">快速添加</h2>
        <div class="preset-grid">
          <button
            v-for="preset in presets"
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
          <span>API Key（DeepSeek / OpenAI 预设需要）</span>
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
                <option value="openai_compat">OpenAI Compatible</option>
                <option value="openai">OpenAI</option>
                <option value="ollama">Ollama</option>
                <option value="custom">Custom</option>
              </select>
            </label>
            <label class="span-2">
              <span>Base URL</span>
              <input v-model="form.base_url" class="field-control" placeholder="https://api.example.com/v1" />
            </label>
            <label>
              <span>API Key</span>
              <input v-model="form.api_key" class="field-control" type="password" placeholder="可选" />
            </label>
            <label>
              <span>Model ID</span>
              <input v-model="form.model_id" class="field-control" placeholder="deepseek-chat" />
            </label>
          </div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary" :disabled="busy">添加 Provider</button>
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
                <button type="button" class="icon-btn" title="测试连接" :disabled="testingId === p.id" @click="testProvider(p.id)">
                  <AppIcon name="zap" :size="16" />
                </button>
                <button type="button" class="icon-btn" title="编辑" @click="startEditProvider(p)">
                  <AppIcon name="pencil" :size="16" />
                </button>
                <button type="button" class="icon-btn danger" title="删除" @click="removeProvider(p)">
                  <AppIcon name="trash" :size="16" />
                </button>
              </div>
            </div>
            <p class="provider-meta">{{ p.base_url }} · {{ p.api_key_masked || '无 Key' }}</p>

            <ul class="model-list">
              <li v-for="m in p.models || []" :key="m.id" class="model-row">
                <template v-if="editingModelId === m.id">
                  <div class="model-edit-grid">
                    <input v-model="modelEdit.display_name" class="field-control" placeholder="显示名称" />
                    <input v-model="modelEdit.model_id" class="field-control" placeholder="model id" />
                    <input v-model.number="modelEdit.context_window" class="field-control" type="number" placeholder="上下文" />
                    <label class="check-label">
                      <input v-model="modelEdit.supports_tools" type="checkbox" />
                      支持工具
                    </label>
                    <label class="check-label">
                      <input v-model="modelEdit.is_default" type="checkbox" />
                      设为默认
                    </label>
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
                  <code class="model-id">{{ m.model_id }}</code>
                  <div class="model-actions">
                    <button type="button" class="icon-btn" title="编辑" @click="startEditModel(m)">
                      <AppIcon name="pencil" :size="15" />
                    </button>
                    <button type="button" class="icon-btn danger" title="删除" @click="removeModel(m, p.name)">
                      <AppIcon name="trash" :size="15" />
                    </button>
                  </div>
                </template>
              </li>
            </ul>
          </template>
        </article>
      </section>

      <p v-if="error" class="status-msg" :class="{ ok: error.startsWith('连接成功') }">{{ error }}</p>
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
.api-key-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
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
  min-width: 0;
  font-size: 10px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
.icon-btn {
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.icon-btn:hover {
  background: var(--code-bg);
  color: var(--text-h);
}
.icon-btn.danger:hover {
  background: color-mix(in srgb, var(--danger) 12%, var(--code-bg));
  color: var(--danger);
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
</style>
