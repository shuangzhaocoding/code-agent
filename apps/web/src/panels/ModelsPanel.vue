<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'

const store = useAppStore()
const error = ref('')
const form = reactive({
  name: 'DeepSeek',
  kind: 'deepseek',
  base_url: 'https://api.deepseek.com/v1',
  api_key: '',
  model_id: 'deepseek-chat',
})

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

async function add() {
  error.value = ''
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
  await store.loadProviders()
}

async function applyPreset(kind: string) {
  error.value = ''
  try {
    await api(`/api/llm/presets/${kind}`, {
      method: 'POST',
      body: JSON.stringify({ api_key: form.api_key || undefined, make_default: true }),
    })
    form.api_key = ''
    await store.loadProviders()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}
</script>

<template>
  <div class="panel-shell">
    <div class="panel-body models">
      <p class="hint">DeepSeek 走官方 OpenAI 兼容接口：<code>https://api.deepseek.com/v1</code></p>
      <div class="quick">
        <button type="button" class="btn btn-primary" @click="applyPreset('deepseek')">添加 DeepSeek</button>
        <button type="button" class="btn" @click="applyPreset('ollama')">添加 Ollama</button>
      </div>
      <p v-if="error" class="err">{{ error }}</p>
      <form @submit.prevent="add">
        <input v-model="form.name" class="field-control" placeholder="名称" />
        <select v-model="form.kind" class="field-control" @change="onKindChange">
          <option value="deepseek">DeepSeek</option>
          <option value="openai_compat">OpenAI Compatible</option>
          <option value="openai">OpenAI</option>
          <option value="ollama">Ollama</option>
          <option value="custom">Custom</option>
        </select>
        <input v-model="form.base_url" class="field-control" placeholder="Base URL" />
        <input v-model="form.api_key" class="field-control" placeholder="API Key（DeepSeek 填 sk-…）" type="password" />
        <input v-model="form.model_id" class="field-control" placeholder="model id，如 deepseek-chat" />
        <button type="submit" class="btn btn-primary">添加</button>
      </form>
      <article v-for="p in store.providers" :key="p.id">
        <h3>{{ p.name }} <small>{{ p.kind }}</small></h3>
        <div class="meta">{{ p.base_url }} · {{ p.api_key_masked || 'no key' }}</div>
        <ul>
          <li v-for="m in p.models" :key="m.id">{{ m.display_name }} <em v-if="m.is_default">默认</em></li>
        </ul>
      </article>
    </div>
  </div>
</template>

<style scoped>
.models { padding: 14px 16px; }
.hint { color: var(--text-secondary); font-size: 13px; margin: 0 0 12px; }
.quick { display: flex; gap: 8px; margin-bottom: 12px; }
form { display: grid; gap: 8px; margin: 12px 0 16px; }
.err { color: var(--danger); font-size: 13px; }
article {
  border-top: 1px solid var(--border);
  padding: 12px 0;
}
h3 { margin: 0 0 4px; font-size: 14px; }
small, em, .meta {
  color: var(--text-secondary);
  font-style: normal;
  font-weight: 400;
}
.meta { font-size: 12px; font-family: var(--mono); }
ul { margin: 8px 0 0; padding-left: 18px; color: var(--text-secondary); }
code { font-family: var(--mono); font-size: 12px; }
</style>
