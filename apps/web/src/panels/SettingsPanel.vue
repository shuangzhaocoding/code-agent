<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'

type SchemaSpec = {
  title?: string
  enum?: string[]
  format?: string
  type?: string
  minimum?: number
  maximum?: number
  default?: unknown
}

const store = useAppStore()
const local = reactive<Record<string, unknown>>({})
const saved = ref(false)

const schema = computed(() => (store.settings?.schema?.properties || {}) as Record<string, SchemaSpec>)

const groups = computed(() => {
  const map = new Map<string, { id: string; title: string; icon: string; keys: string[] }>()
  const defs: Record<string, { title: string; icon: string }> = {
    agent: { title: 'Agent', icon: 'sparkles' },
    policy: { title: '策略与安全', icon: 'shield' },
    terminal: { title: '终端', icon: 'terminal' },
    llm: { title: '模型', icon: 'chip' },
    ui: { title: '界面', icon: 'sliders' },
  }
  for (const key of Object.keys(schema.value)) {
    const prefix = key.split('.')[0] || 'other'
    const def = defs[prefix] || { title: prefix, icon: 'settings' }
    const group = map.get(prefix) || { id: prefix, title: def.title, icon: def.icon, keys: [] }
    group.keys.push(key)
    map.set(prefix, group)
  }
  return [...map.values()]
})

onMounted(async () => {
  await store.loadSettings()
  Object.assign(local, store.settings?.values || {})
})

watch(
  () => store.settings,
  (s) => {
    if (s) Object.assign(local, s.values)
  },
)

function specFor(key: string) {
  return schema.value[key] || {}
}

function enumLabel(key: string, value: string) {
  const labels: Record<string, Record<string, string>> = {
    'agent.default_mode': { ask: 'Ask · 问答', agent: 'Agent · 代理', plan: 'Plan · 规划' },
    'policy.auto_run': { manual: '手动确认', sandbox: '沙箱自动', full: '完全自动' },
    'ui.theme': { dark: '深色', light: '浅色' },
  }
  return labels[key]?.[value] || value
}

async function save() {
  await store.saveSettings({ ...local })
  saved.value = true
  setTimeout(() => { saved.value = false }, 2000)
}
</script>

<template>
  <div class="panel-shell settings-panel">
    <div class="panel-body">
      <header class="page-head">
        <div>
          <h1 class="page-title">设置</h1>
          <p class="page-lead">覆盖工作区配置。优先级：default.yaml → 用户配置 → 工作区 .code-agent/config.yaml → 本页。</p>
        </div>
        <button type="button" class="btn btn-primary" :class="{ saved }" @click="save">
          <AppIcon :name="saved ? 'check' : 'save'" :size="14" />
          {{ saved ? '已保存' : '保存设置' }}
        </button>
      </header>

      <div class="settings-grid">
        <section v-for="group in groups" :key="group.id" class="settings-group">
          <div class="group-head">
            <span class="group-icon"><AppIcon :name="group.icon" :size="18" /></span>
            <h2>{{ group.title }}</h2>
          </div>

          <div v-for="key in group.keys" :key="key" class="setting-row">
            <div class="setting-copy">
              <label :for="key">{{ specFor(key).title || key }}</label>
              <code v-if="key.includes('.')" class="setting-key">{{ key }}</code>
            </div>

            <select
              v-if="specFor(key).enum"
              :id="key"
              v-model="local[key]"
              class="field-control setting-input"
            >
              <option v-for="opt in specFor(key).enum" :key="opt" :value="opt">
                {{ enumLabel(key, opt) }}
              </option>
            </select>

            <textarea
              v-else-if="specFor(key).format === 'textarea'"
              :id="key"
              v-model="local[key] as string"
              class="field-control setting-input"
              rows="4"
            />

            <label v-else-if="specFor(key).type === 'boolean'" class="toggle">
              <input :id="key" v-model="local[key]" type="checkbox" />
              <span class="toggle-track" />
            </label>

            <input
              v-else-if="specFor(key).type === 'integer' || specFor(key).type === 'number'"
              :id="key"
              v-model.number="local[key]"
              class="field-control setting-input"
              type="number"
              :min="specFor(key).minimum"
              :max="specFor(key).maximum"
              step="any"
            />

            <input v-else :id="key" v-model="local[key]" class="field-control setting-input" />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-panel .panel-body {
  padding: 16px 20px 24px;
  overflow: auto;
  font-size: 12px;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.page-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-h);
}
.page-lead {
  margin: 0;
  max-width: 520px;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
}
.page-head .btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  height: 30px;
  padding: 0 12px;
  font-size: 12px;
}
.page-head .btn.saved {
  background: color-mix(in srgb, var(--primary) 80%, #059669);
}
.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.settings-group {
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  padding: 12px 14px;
}
.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: var(--border-width) solid var(--border);
}
.group-icon {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--primary-soft);
  color: var(--primary);
  flex-shrink: 0;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 16%, transparent);
}
.group-head h2 {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}
.setting-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 0;
  border-bottom: var(--border-width) solid var(--border);
}
.setting-row:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}
.setting-copy label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}
.setting-key {
  display: block;
  margin-top: 1px;
  font-size: 10px;
  font-family: var(--mono);
  color: var(--text-muted);
}
.setting-input {
  width: 100%;
  font-size: 12px;
  padding: 6px 9px;
}
.setting-input.field-control {
  min-height: 30px;
}
.toggle {
  position: relative;
  width: 40px;
  height: 22px;
  cursor: pointer;
}
.toggle input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.toggle-track {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: var(--code-bg);
  border: var(--border-width) solid var(--border);
  transition: background 0.15s ease, border-color 0.15s ease;
}
.toggle-track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--panel-bg);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  transition: transform 0.15s ease;
}
.toggle input:checked + .toggle-track {
  background: var(--primary-soft);
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
}
.toggle input:checked + .toggle-track::after {
  transform: translateX(18px);
  background: var(--primary);
}</style>
