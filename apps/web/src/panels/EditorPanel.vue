<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { currentTheme } from '@/theme'
import FileTreeIcon from '@/components/FileTreeIcon.vue'
import AppIcon from '@/components/AppIcon.vue'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import ContextMenu, { type ContextMenuItem } from '@/components/ContextMenu.vue'
import FilePreviewHost from '@/preview/FilePreviewHost.vue'
import { isPreviewKind } from '@/preview/classify'

const store = useAppStore()
const host = ref<HTMLDivElement | null>(null)
const diffHost = ref<HTMLDivElement | null>(null)
const mdPreview = ref(false)
/** HTML: true = iframe preview, false = Monaco source */
const htmlPreview = ref(true)
const tabMenu = ref<{ x: number; y: number; path: string } | null>(null)
let editor: import('monaco-editor').editor.IStandaloneCodeEditor | null = null
let diffEditor: import('monaco-editor').editor.IStandaloneDiffEditor | null = null
let monacoMod: typeof import('monaco-editor') | null = null
const models = new Map<string, import('monaco-editor').editor.ITextModel>()
const origModels = new Map<string, import('monaco-editor').editor.ITextModel>()
const review = computed(() => store.pendingReview(store.activePath))
const pendingCount = computed(() => store.pendingReviews.length)
const reviewIndex = computed(() => {
  const i = store.pendingReviews.findIndex((r) => r.path === store.activePath)
  return i < 0 ? 0 : i + 1
})

const isHtmlFile = computed(() => store.openFile?.kind === 'html')
const canHtmlPreview = computed(() => Boolean(isHtmlFile.value && !review.value))
const showHtmlPreview = computed(() => htmlPreview.value && canHtmlPreview.value)

const activeIsBinaryPreview = computed(() => {
  const f = store.openFile
  return Boolean(f && isPreviewKind(f.kind) && f.kind !== 'html')
})

const showFilePreview = computed(() => activeIsBinaryPreview.value || showHtmlPreview.value)

function cssColor(name: string, fallback: string) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
  if (raw.startsWith('#')) {
    if (raw.length === 4) return `#${raw[1]}${raw[1]}${raw[2]}${raw[2]}${raw[3]}${raw[3]}`
    return raw
  }
  const m = raw.match(/rgba?\((\d+)[,\s]+(\d+)[,\s]+(\d+)/)
  if (!m) return fallback
  return `#${[m[1], m[2], m[3]].map((n) => Number(n).toString(16).padStart(2, '0')).join('')}`
}

function applyEditorTheme() {
  if (!monacoMod) return
  const dark = currentTheme() === 'dark'
  const bg = cssColor('--editor-bg', dark ? '#161a22' : '#ffffff')
  monacoMod.editor.defineTheme('ca-editor', {
    base: dark ? 'vs-dark' : 'vs',
    inherit: true,
    rules: [],
    colors: {
      'editor.background': bg,
      'editorGutter.background': bg,
      'editorStickyScroll.background': bg,
      'minimap.background': bg,
    },
  })
  monacoMod.editor.setTheme('ca-editor')
}

function langOf(path: string) {
  const ext = path.split('.').pop() || ''
  const langMap: Record<string, string> = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    vue: 'html',
    py: 'python',
    md: 'markdown',
    json: 'json',
    css: 'css',
    html: 'html',
    yaml: 'yaml',
    yml: 'yaml',
  }
  return langMap[ext] || 'plaintext'
}

function fileName(path: string) {
  return path.split('/').pop() || path
}

function isMarkdownFile(path: string) {
  return /\.(md|mdx|markdown)$/i.test(path)
}

const canMarkdownPreview = computed(
  () => Boolean(store.activePath && store.openFile?.kind === 'text' && isMarkdownFile(store.activePath)),
)
const showMarkdownPreview = computed(() => mdPreview.value && canMarkdownPreview.value && !review.value)

const canSave = computed(
  () =>
    Boolean(store.openFile) &&
    !review.value &&
    !showMarkdownPreview.value &&
    !activeIsBinaryPreview.value &&
    !(isHtmlFile.value && htmlPreview.value),
)

function uriOf(path: string, original = false) {
  return monacoMod!.Uri.from({
    scheme: 'inmemory',
    authority: original ? 'ca-orig' : 'ca',
    path: `/${path}`,
  })
}

function ensureModel(path: string, content: string) {
  if (!monacoMod) return null
  let model = models.get(path)
  if (!model || model.isDisposed()) {
    const existing = monacoMod.editor.getModel(uriOf(path))
    model = existing || monacoMod.editor.createModel(content, langOf(path), uriOf(path))
    monacoMod.editor.setModelLanguage(model, langOf(path))
    model.onDidChangeContent(() => {
      store.updateOpenContent(path, model!.getValue())
    })
    models.set(path, model)
  }
  if (model.getValue() !== content) model.setValue(content)
  return model
}

function ensureOrigModel(path: string, content: string) {
  if (!monacoMod) return null
  let model = origModels.get(path)
  if (!model || model.isDisposed()) {
    const existing = monacoMod.editor.getModel(uriOf(path, true))
    model = existing || monacoMod.editor.createModel(content, langOf(path), uriOf(path, true))
    origModels.set(path, model)
  }
  if (model.getValue() !== content) model.setValue(content)
  return model
}

const editorOptions = {
  automaticLayout: true,
  minimap: { enabled: false },
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  fontSize: 13,
  scrollBeyondLastLine: false,
  padding: { top: 12 },
  scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
}

function showPath(path: string | null) {
  if (!monacoMod) return
  if (review.value && path) {
    showDiff(path, review.value.before, review.value.after)
    return
  }
  diffEditor?.setModel(null)
  if (!editor) return
  const file = path ? store.openFiles.find((f) => f.path === path) : null
  if (!path || !file) {
    editor.setModel(null)
    return
  }
  // Binary / media previews, or HTML while in preview mode — hide Monaco
  if (isPreviewKind(file.kind) && (file.kind !== 'html' || htmlPreview.value)) {
    editor.setModel(null)
    return
  }
  const model = ensureModel(path, file.content ?? '')
  if (model) editor.setModel(model)
  requestAnimationFrame(() => editor?.layout())
}

function showDiff(path: string, before: string, after: string) {
  if (!monacoMod || !diffHost.value) return
  if (!diffEditor) {
    diffEditor = monacoMod.editor.createDiffEditor(diffHost.value, {
      ...editorOptions,
      theme: 'ca-editor',
      readOnly: true,
      originalEditable: false,
      renderSideBySide: true,
      ignoreTrimWhitespace: false,
    })
  }
  const original = ensureOrigModel(path, before)
  const modified = ensureModel(path, after)
  if (original && modified) diffEditor.setModel({ original, modified })
  requestAnimationFrame(() => diffEditor?.layout())
}

onMounted(async () => {
  monacoMod = await import('monaco-editor')
  const { default: editorWorker } = await import('monaco-editor/editor/editor.worker.js?worker')
  self.MonacoEnvironment = {
    getWorker: () => new editorWorker(),
  }
  if (!host.value) return
  applyEditorTheme()
  editor = monacoMod.editor.create(host.value, {
    value: '',
    language: 'plaintext',
    theme: 'ca-editor',
    ...editorOptions,
  })
  showPath(store.activePath)
  window.addEventListener('ca-theme', onTheme as EventListener)
  window.addEventListener('keydown', onKey)
  window.addEventListener('ca-file-reload', onReload as EventListener)
})

function onTheme() {
  applyEditorTheme()
}

function onKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    save()
  }
}

function onReload(e: Event) {
  const detail = (e as CustomEvent<{ path: string; content: string }>).detail
  if (!detail?.path) return
  const model = models.get(detail.path)
  if (model && model.getValue() !== detail.content) model.setValue(detail.content)
  const current = store.pendingReview(detail.path)
  if (current && store.activePath === detail.path) {
    showDiff(detail.path, current.before, current.after)
  }
}

watch(
  () => [store.activePath, review.value?.blockId, review.value?.status, htmlPreview.value] as const,
  async () => {
    await nextTick()
    showPath(store.activePath)
  },
)

watch(
  () => store.activePath,
  (path, prev) => {
    if (!path || !prev || !isMarkdownFile(path) || !isMarkdownFile(prev)) mdPreview.value = false
    // Reset HTML to preview when switching between different HTML files / leaving HTML
    const nextHtml = path ? /\.(html?|HTML?)$/.test(path) : false
    const prevHtml = prev ? /\.(html?|HTML?)$/.test(prev) : false
    if (!nextHtml || !prevHtml || path !== prev) htmlPreview.value = true
  },
)

watch(
  () => store.openFiles.map((f) => f.path).join('\0'),
  () => {
    const keep = new Set(store.openFiles.map((f) => f.path))
    for (const [path, model] of models) {
      if (!keep.has(path)) {
        if (editor?.getModel() === model) editor.setModel(null)
        model.dispose()
        models.delete(path)
      }
    }
    for (const [path, model] of origModels) {
      if (!keep.has(path)) {
        model.dispose()
        origModels.delete(path)
      }
    }
  },
)

onBeforeUnmount(() => {
  window.removeEventListener('ca-theme', onTheme as EventListener)
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('ca-file-reload', onReload as EventListener)
  for (const model of models.values()) model.dispose()
  for (const model of origModels.values()) model.dispose()
  models.clear()
  origModels.clear()
  diffEditor?.dispose()
  editor?.dispose()
})

async function save() {
  await store.saveOpenFile()
}

function onTabWheel(e: WheelEvent) {
  const el = e.currentTarget as HTMLElement
  if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
    el.scrollLeft += e.deltaY
    e.preventDefault()
  }
}

function onTabAux(path: string, e: MouseEvent) {
  if (e.button === 1) {
    e.preventDefault()
    store.closeFile(path)
  }
}

function onTabContext(path: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  tabMenu.value = { x: e.clientX, y: e.clientY, path }
}

const tabMenuItems = computed((): ContextMenuItem[] => {
  const path = tabMenu.value?.path
  if (!path) return []
  const files = store.openFiles
  const index = files.findIndex((f) => f.path === path)
  return [
    { id: 'close', label: '关闭', icon: 'close' },
    { id: 'close-others', label: '关闭其他', icon: 'close-others', disabled: files.length < 2 },
    { id: 'close-right', label: '关闭右侧', icon: 'close-right', disabled: index < 0 || index >= files.length - 1 },
    { id: 'close-all', label: '关闭全部', icon: 'close-all', disabled: files.length === 0 },
    { id: 'sep-copy', separator: true },
    { id: 'copy-path', label: '复制路径', icon: 'copy' },
  ]
})

const tabMenuActions: Record<string, (path: string) => void | Promise<void>> = {
  close: (path) => store.closeFile(path),
  'close-others': (path) => store.closeOtherFiles(path),
  'close-right': (path) => store.closeFilesToTheRight(path),
  'close-all': () => store.closeAllFiles(),
  'copy-path': async (path) => {
    try {
      await navigator.clipboard.writeText(path)
    } catch {
      /* ignore */
    }
  },
}

async function onTabMenuSelect(id: string) {
  const path = tabMenu.value?.path
  if (!path) return
  await tabMenuActions[id]?.(path)
}
</script>

<template>
  <div class="panel-shell editor-shell">
    <header class="file-bar">
      <div class="tabs" @wheel="onTabWheel">
        <button
          v-for="file in store.openFiles"
          :key="file.path"
          type="button"
          class="ftab"
          :class="{ active: store.activePath === file.path }"
          :title="file.path"
          @click="store.activateFile(file.path)"
          @auxclick="onTabAux(file.path, $event)"
          @contextmenu="onTabContext(file.path, $event)"
        >
          <FileTreeIcon kind="file" :path="file.path" :size="16" />
          <span class="name">{{ fileName(file.path) }}{{ file.dirty ? ' •' : '' }}</span>
          <span v-if="store.pendingReview(file.path)" class="mark">diff</span>
          <span class="x" title="关闭" @click.stop="store.closeFile(file.path)">×</span>
        </button>
      </div>
      <div v-if="canMarkdownPreview" class="md-toggle" role="group" aria-label="Markdown 预览">
        <button type="button" class="md-toggle-btn" :class="{ 'is-on': !mdPreview }" @click="mdPreview = false">Markdown</button>
        <button type="button" class="md-toggle-btn" :class="{ 'is-on': mdPreview }" @click="mdPreview = true">预览</button>
      </div>
      <div v-if="canHtmlPreview" class="md-toggle" role="group" aria-label="HTML 预览">
        <button type="button" class="md-toggle-btn" :class="{ 'is-on': !htmlPreview }" @click="htmlPreview = false">源码</button>
        <button type="button" class="md-toggle-btn" :class="{ 'is-on': htmlPreview }" @click="htmlPreview = true">预览</button>
      </div>
      <button type="button" class="btn" :disabled="!canSave" @click="save">保存</button>
    </header>
    <div v-if="store.fileNotice" class="file-notice" role="status">
      <span>{{ store.fileNotice }}</span>
      <button type="button" class="notice-x" @click="store.clearFileNotice()">×</button>
    </div>
    <div v-if="pendingCount" class="review-bar">
      <span>{{ review ? '请确认当前文件 diff' : '有待确认的改动' }}</span>
      <span class="count">{{ review ? `${reviewIndex}/${pendingCount}` : `${pendingCount} 个文件` }}</span>
      <button type="button" class="btn ghost" :disabled="pendingCount < 2" @click="store.cycleReview(-1)">上一个</button>
      <button type="button" class="btn ghost" :disabled="pendingCount < 2" @click="store.cycleReview(1)">下一个</button>
      <span class="spacer" />
      <button v-if="review" type="button" class="btn ghost" @click="store.rejectReview(review.path)">拒绝</button>
      <button v-if="review" type="button" class="btn primary" @click="store.acceptReview(review.path)">接受</button>
      <button type="button" class="btn primary" @click="store.acceptAllReviews()">全部接受</button>
    </div>
    <div class="host-wrap">
      <FilePreviewHost
        v-if="showFilePreview && store.openFile"
        :file="store.openFile"
        class="host"
      />
      <MarkdownPreview
        v-else-if="showMarkdownPreview && store.openFile"
        :content="store.openFile.content"
        :path="store.openFile.path"
        class="host"
      />
      <div ref="host" class="host" :class="{ hidden: !!review || showMarkdownPreview || showFilePreview }" />
      <div ref="diffHost" class="host" :class="{ hidden: !review }" />
      <div v-if="!store.openFile" class="empty">
        <AppIcon name="file" :size="28" />
        <p>从侧栏打开文件</p>
      </div>
    </div>
    <ContextMenu
      v-if="tabMenu"
      :x="tabMenu.x"
      :y="tabMenu.y"
      :items="tabMenuItems"
      @select="onTabMenuSelect"
      @close="tabMenu = null"
    />
  </div>
</template>

<style scoped>
.editor-shell { background: var(--editor-bg); }
.file-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding-right: 8px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--bg);
}
.file-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 0 12px;
  border-bottom: var(--border-width) solid var(--border);
  background: color-mix(in srgb, #dc2626 12%, var(--bg));
  color: var(--text-h);
  font-size: 12.5px;
}
.file-notice span {
  flex: 1;
  min-width: 0;
}
.notice-x {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}
.tabs {
  flex: 1;
  min-width: 0;
  display: flex;
  overflow-x: auto;
  scrollbar-width: none;
}
.tabs::-webkit-scrollbar { display: none; }
.ftab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 8px 0 12px;
  border: 0;
  border-right: var(--border-width) solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12.5px;
  max-width: 200px;
  flex-shrink: 0;
}
.ftab:hover { background: var(--bg-muted); color: var(--text); }
.ftab.active {
  background: var(--editor-bg);
  color: var(--text);
  box-shadow: inset 0 -2px 0 var(--primary);
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mark {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  color: var(--primary);
  background: var(--primary-soft);
  border-radius: 4px;
  padding: 0 4px;
  line-height: 16px;
}
.md-toggle {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 2px;
  border: var(--border-width) solid var(--border);
  border-radius: 8px;
  background: var(--code-bg);
  flex-shrink: 0;
}
.md-toggle-btn {
  height: 22px;
  padding: 0 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 12px;
  line-height: 22px;
  white-space: nowrap;
  cursor: pointer;
}
.md-toggle-btn.is-on {
  background: var(--panel-bg);
  color: var(--text-h);
}
.review-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 0 10px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--primary-soft);
  color: var(--text);
  font-size: 12.5px;
}
.count {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--text-secondary);
}
.review-bar .btn { margin: 0; height: 26px; }
.spacer { flex: 1; }
.btn.ghost {
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text-secondary);
}
.btn.primary {
  border: 1px solid color-mix(in srgb, var(--primary) 45%, var(--border));
  background: var(--bg-elevated);
  color: var(--primary);
}
.x {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  font-size: 14px;
  line-height: 1;
}
.ftab:hover .x,
.ftab.active .x { opacity: 0.55; }
.x:hover { opacity: 1 !important; background: var(--bg-muted); }
.btn {
  height: auto;
  margin: 4px 8px;
  padding: 0 10px;
  font-size: 12px;
}
.host-wrap {
  flex: 1;
  min-height: 0;
  position: relative;
  background: var(--editor-bg);
}
.host {
  height: 100%;
  background: var(--editor-bg);
}
.host.hidden { display: none; }
.empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
  font-size: 13px;
  background: var(--editor-bg);
}
.empty p { margin: 0; }
</style>
