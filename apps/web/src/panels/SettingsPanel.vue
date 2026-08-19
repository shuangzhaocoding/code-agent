<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import { useAppStore } from '@/stores/app'

type SchemaSpec = {
  title?: string
  enum?: string[]
  format?: string
  type?: string
}

const store = useAppStore()
const local = reactive<Record<string, unknown>>({})
const schema = computed(() => (store.settings?.schema?.properties || {}) as Record<string, SchemaSpec>)

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

async function save() {
  await store.saveSettings({ ...local })
}
</script>

<template>
  <div class="panel-shell">
    <div class="panel-body settings">
      <div class="page-panel setup__card">
        <p>配置分层：default.yaml → ~/.code-agent/config.yaml → 工作区 .code-agent/config.yaml → 本页覆盖。</p>
        <div v-for="(spec, key) in schema" :key="key" class="field">
          <label>{{ spec.title || key }}</label>
          <select v-if="spec.enum" v-model="local[key]" class="field-control">
            <option v-for="opt in spec.enum" :key="opt" :value="opt">{{ opt }}</option>
          </select>
          <textarea v-else-if="spec.format === 'textarea'" v-model="local[key]" class="field-control" rows="4" />
          <input v-else-if="spec.type === 'boolean'" type="checkbox" v-model="local[key]" />
          <input v-else-if="spec.type === 'integer' || spec.type === 'number'" type="number" v-model.number="local[key]" class="field-control" />
          <input v-else v-model="local[key]" class="field-control" />
        </div>
        <button type="button" class="btn btn-primary" @click="save">保存</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings { padding: 16px 20px; }
p { color: var(--text); font-size: 13px; margin: 0 0 16px; }
.field {
  margin: 0 0 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
label { font-size: 13px; color: var(--text-h); font-weight: 600; }
</style>
