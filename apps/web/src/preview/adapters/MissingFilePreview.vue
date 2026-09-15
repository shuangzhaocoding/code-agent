<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { t } from '@/i18n'
import type { PreviewProps } from '@/preview/types'
import { useAppStore } from '@/stores/app'

const props = defineProps<PreviewProps>()
const store = useAppStore()
const retrying = ref(false)

const fileName = computed(() => props.path.split('/').filter(Boolean).pop() || props.path)

async function retry() {
  if (retrying.value) return
  retrying.value = true
  try {
    await store.retryOpenPath(props.path)
  } finally {
    retrying.value = false
  }
}

function reveal() {
  window.dispatchEvent(new CustomEvent('ca-reveal-in-tree', { detail: { path: props.path } }))
}

function closeTab() {
  store.closeFile(props.path)
}
</script>

<template>
  <div class="preview-pane missing-file">
    <div class="card">
      <div class="icon-wrap" aria-hidden="true">
        <AppIcon name="file" :size="28" :stroke-width="1.5" />
      </div>
      <h3>{{ t('file.notFoundTitle') }}</h3>
      <p class="lead">{{ t('file.notFound') }}</p>
      <p class="path" :title="path">{{ path }}</p>
      <dl>
        <div>
          <dt>{{ t('file.name') }}</dt>
          <dd>{{ fileName }}</dd>
        </div>
      </dl>
      <div class="actions">
        <button type="button" class="btn btn-primary" :disabled="retrying" @click="retry">
          <AppIcon name="refresh" :size="12" :stroke-width="1.75" />
          {{ retrying ? t('file.retrying') : t('file.retryOpen') }}
        </button>
        <button type="button" class="btn" @click="reveal">
          <AppIcon name="tree" :size="12" :stroke-width="1.75" />
          {{ t('editor.revealInExplorer') }}
        </button>
        <button type="button" class="btn" @click="closeTab">
          <AppIcon name="close" :size="12" :stroke-width="1.75" />
          {{ t('file.closeTab') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.missing-file {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 24px;
  box-sizing: border-box;
  background: var(--editor-bg);
}
.card {
  max-width: 440px;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel-bg);
  padding: 22px 24px;
  box-shadow: var(--shadow-md);
}
.icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  margin-bottom: 12px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--text-secondary) 10%, transparent);
  color: var(--text-secondary);
}
h3 {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-h);
}
.lead {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text);
}
.path {
  margin: 0 0 14px;
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
  font-family: var(--mono);
}
dl {
  margin: 0 0 16px;
  display: grid;
  gap: 8px;
}
dl > div {
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: 8px;
  font-size: 12.5px;
}
dt {
  color: var(--text-secondary);
}
dd {
  margin: 0;
  color: var(--text-h);
  word-break: break-all;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-h);
  font-size: 12px;
  cursor: pointer;
}
.btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text-h) 6%, var(--bg));
}
.btn:disabled {
  opacity: 0.6;
  cursor: default;
}
.btn-primary {
  border-color: transparent;
  background: var(--primary);
  color: #fff;
}
.btn-primary:hover:not(:disabled) {
  filter: brightness(1.05);
  background: var(--primary-hover);
}
</style>
