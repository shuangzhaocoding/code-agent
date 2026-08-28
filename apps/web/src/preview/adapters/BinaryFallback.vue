<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { PreviewProps } from '@/preview/types'

const props = defineProps<PreviewProps>()
const sizeLabel = ref('')

onMounted(async () => {
  try {
    const res = await fetch(props.previewUrl, { method: 'HEAD' })
    const len = res.headers.get('content-length')
    if (len) {
      const n = Number(len)
      if (n < 1024) sizeLabel.value = `${n} B`
      else if (n < 1024 * 1024) sizeLabel.value = `${(n / 1024).toFixed(1)} KB`
      else sizeLabel.value = `${(n / (1024 * 1024)).toFixed(1)} MB`
    }
  } catch {
    /* ignore */
  }
})

const fileName = computed(() => props.path.split('/').pop() || props.path)
</script>

<template>
  <div class="preview-pane binary-fallback">
    <div class="card">
      <h3>无法内嵌预览</h3>
      <p class="path">{{ path }}</p>
      <dl>
        <div>
          <dt>文件名</dt>
          <dd>{{ fileName }}</dd>
        </div>
        <div v-if="mime">
          <dt>类型</dt>
          <dd>{{ mime }}</dd>
        </div>
        <div v-if="sizeLabel">
          <dt>大小</dt>
          <dd>{{ sizeLabel }}</dd>
        </div>
      </dl>
      <a class="btn btn-primary" :href="previewUrl" target="_blank" rel="noopener noreferrer">在新标签打开 / 下载</a>
    </div>
  </div>
</template>

<style scoped>
.binary-fallback {
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
  max-width: 420px;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel-bg);
  padding: 20px 22px;
  box-shadow: var(--shadow-md);
}
h3 {
  margin: 0 0 8px;
  font-size: 15px;
  color: var(--text-h);
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
  grid-template-columns: 56px 1fr;
  gap: 8px;
  font-size: 12.5px;
}
dt {
  color: var(--text-secondary);
}
dd {
  margin: 0;
  color: var(--text-h);
  font-family: var(--mono);
}
</style>
