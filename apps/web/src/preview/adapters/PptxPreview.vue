<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import JSZip from 'jszip'
import type { PreviewProps } from '@/preview/types'

const props = defineProps<PreviewProps>()
const error = ref('')
const loading = ref(true)
const slides = ref<{ index: number; texts: string[] }[]>([])
const active = ref(0)

function decodeXmlEntities(s: string) {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
}

function extractTexts(xml: string): string[] {
  const texts: string[] = []
  const re = /<a:t(?:\s[^>]*)?>([\s\S]*?)<\/a:t>/g
  let m: RegExpExecArray | null
  while ((m = re.exec(xml))) {
    const t = decodeXmlEntities(m[1]).trim()
    if (t) texts.push(t)
  }
  return texts
}

async function load() {
  loading.value = true
  error.value = ''
  slides.value = []
  active.value = 0
  try {
    const res = await fetch(props.previewUrl)
    if (!res.ok) throw new Error(await res.text())
    const buf = await res.arrayBuffer()
    const zip = await JSZip.loadAsync(buf)
    const names = Object.keys(zip.files)
      .filter((n) => /^ppt\/slides\/slide\d+\.xml$/i.test(n))
      .sort((a, b) => {
        const na = Number(a.match(/slide(\d+)/i)?.[1] || 0)
        const nb = Number(b.match(/slide(\d+)/i)?.[1] || 0)
        return na - nb
      })
    const next: { index: number; texts: string[] }[] = []
    for (let i = 0; i < names.length; i++) {
      const xml = await zip.files[names[i]].async('string')
      next.push({ index: i + 1, texts: extractTexts(xml) })
    }
    slides.value = next
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

const current = computed(() => slides.value[active.value] || null)

onMounted(() => {
  void load()
})
watch(
  () => props.previewUrl,
  () => {
    void load()
  },
)
</script>

<template>
  <div class="preview-pane pptx-preview">
    <p v-if="loading" class="status">正在解析幻灯片…</p>
    <p v-else-if="error" class="status err">{{ error }}</p>
    <template v-else-if="slides.length">
      <div class="toolbar">
        <button type="button" class="ghost-btn nav" :disabled="active <= 0" @click="active = Math.max(0, active - 1)">上一页</button>
        <span class="page">{{ active + 1 }} / {{ slides.length }}</span>
        <button
          type="button"
          class="ghost-btn nav"
          :disabled="active >= slides.length - 1"
          @click="active = Math.min(slides.length - 1, active + 1)"
        >
          下一页
        </button>
      </div>
      <div class="slide">
        <h3>幻灯片 {{ current?.index }}</h3>
        <ul v-if="current?.texts.length">
          <li v-for="(t, i) in current.texts" :key="i">{{ t }}</li>
        </ul>
        <p v-else class="muted">（此页无可提取文本）</p>
      </div>
      <div class="thumbs">
        <button
          v-for="(s, i) in slides"
          :key="s.index"
          type="button"
          class="chip thumb"
          :class="{ on: i === active }"
          @click="active = i"
        >
          {{ s.index }}
        </button>
      </div>
    </template>
    <p v-else class="status">未找到幻灯片</p>
  </div>
</template>

<style scoped>
.pptx-preview {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--editor-bg);
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.nav {
  padding: 0 10px;
}
.nav:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.page {
  font-size: 12.5px;
  color: var(--text-secondary);
  font-family: var(--mono);
}
.slide {
  flex: 1;
  overflow: auto;
  padding: 20px 24px;
}
.slide h3 {
  margin: 0 0 12px;
  font-size: 15px;
  color: var(--text-h);
}
.slide ul {
  margin: 0;
  padding-left: 1.2em;
  color: var(--text);
  line-height: 1.6;
  font-size: 14px;
}
.muted {
  color: var(--text-secondary);
  font-size: 13px;
}
.thumbs {
  display: flex;
  gap: 4px;
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  overflow-x: auto;
  flex-shrink: 0;
}
.thumb {
  min-width: var(--ghost-btn-height);
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  border-radius: var(--ghost-btn-radius);
  padding: 0 8px;
  height: var(--ghost-btn-height);
  font-size: var(--ghost-btn-font-size);
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s ease, color 0.12s ease;
}
.thumb:hover:not(.on) {
  opacity: var(--ghost-hover-opacity);
  color: var(--text-h);
}
.thumb.on {
  color: var(--primary);
  opacity: 1;
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
</style>
