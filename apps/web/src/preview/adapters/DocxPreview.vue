<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { renderAsync } from 'docx-preview'
import type { PreviewProps } from '@/preview/types'

const props = defineProps<PreviewProps>()
const host = ref<HTMLElement | null>(null)
const error = ref('')
const loading = ref(true)

async function render() {
  if (!host.value) return
  loading.value = true
  error.value = ''
  host.value.innerHTML = ''
  try {
    const res = await fetch(props.previewUrl)
    if (!res.ok) throw new Error(await res.text())
    const buf = await res.arrayBuffer()
    await renderAsync(buf, host.value, undefined, {
      className: 'docx-preview-body',
      inWrapper: true,
      ignoreWidth: false,
      breakPages: true,
    })
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void render()
})
watch(
  () => props.previewUrl,
  () => {
    void render()
  },
)
</script>

<template>
  <div class="preview-pane docx-preview">
    <p v-if="loading" class="status">正在渲染 Word…</p>
    <p v-else-if="error" class="status err">{{ error }}</p>
    <div ref="host" class="docx-host" />
  </div>
</template>

<style scoped>
.docx-preview {
  width: 100%;
  height: 100%;
  overflow: auto;
  padding: 16px;
  box-sizing: border-box;
  background: var(--bg-muted);
}
.docx-host {
  margin: 0 auto;
  max-width: 900px;
}
.status {
  margin: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}
.status.err {
  color: var(--danger, #dc2626);
}
.docx-preview :deep(.docx-wrapper) {
  background: transparent;
  padding: 0;
}
.docx-preview :deep(.docx-wrapper > section.docx) {
  background: #fff;
  box-shadow: var(--shadow-md);
  margin-bottom: 16px;
  color: #111;
}
</style>
