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
import { langOf } from '@/utils/editorLang'
import { t } from '@/i18n'

const store = useAppStore()
const host = ref<HTMLDivElement | null>(null)
const tabsEl = ref<HTMLElement | null>(null)
const diffHost = ref<HTMLDivElement | null>(null)
const mdPreview = ref(false)
/** HTML: true = iframe preview, false = Monaco source */
const htmlPreview = ref(false)
const tabMenu = ref<{ x: number; y: number; path: string } | null>(null)
let editor: import('monaco-editor').editor.IStandaloneCodeEditor | null = null
let diffEditor: import('monaco-editor').editor.IStandaloneDiffEditor | null = null
let monacoMod: typeof import('monaco-editor') | null = null
let reviewNavDisposables: import('monaco-editor').IDisposable[] = []
let diffRevealDisposable: import('monaco-editor').IDisposable | null = null
const models = new Map<string, import('monaco-editor').editor.ITextModel>()
const origModels = new Map<string, import('monaco-editor').editor.ITextModel>()
let searchDecorations: string[] = []
let lastSearchHighlight: { path: string; line: number; query: string; caseSensitive?: boolean } | null = null
const review = computed(() => store.pendingReview(store.activePath))
const pendingCount = computed(() => store.pendingReviews.length)
const fileReviewCount = computed(() => store.pendingReviewCount(store.activePath))
const fileReviewIndex = computed(() => store.activeReviewIndexFor(store.activePath) + 1)
const filePendingPathCount = computed(() => store.pendingReviewPaths.length)
const filePathIndex = computed(() => {
  const i = store.pendingReviewPaths.indexOf(store.activePath || '')
  return i < 0 ? 0 : i + 1
})
const canCycleDiff = computed(() => fileReviewCount.value > 1)
const canCycleFile = computed(() => filePendingPathCount.value > 1)

function cycleDiff(delta: number) {
  const path = store.activePath
  if (!path || !canCycleDiff.value) return
  store.cycleFileReview(path, delta)
}

async function cycleFile(delta: number) {
  if (!canCycleFile.value) return
  await store.cycleReviewPath(delta)
}

const bulkConfirm = ref<'accept' | 'reject' | null>(null)
const bulkActionRef = ref<HTMLElement | null>(null)

function openBulkConfirm(kind: 'accept' | 'reject') {
  bulkConfirm.value = bulkConfirm.value === kind ? null : kind
}

function closeBulkConfirm() {
  bulkConfirm.value = null
}

async function confirmBulk() {
  const kind = bulkConfirm.value
  if (!kind) return
  bulkConfirm.value = null
  if (kind === 'accept') await store.acceptAllReviews()
  else await store.rejectAllReviews()
}

function onBulkDocClick(e: MouseEvent) {
  if (!bulkConfirm.value) return
  const root = bulkActionRef.value
  if (root && !root.contains(e.target as Node)) closeBulkConfirm()
}

function onBulkKey(e: KeyboardEvent) {
  if (e.key === 'Escape') closeBulkConfirm()
}

watch(pendingCount, (n) => {
  if (!n) closeBulkConfirm()
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

function fileName(path: string) {
  const head = path.startsWith('HEAD:')
  const raw = head ? path.slice(5) : path
  const name = raw.split('/').pop() || raw
  return head ? `${name} (HEAD)` : name
}

function isMarkdownFile(path: string) {
  return /\.(md|mdx|markdown)$/i.test(path)
}

const canMarkdownPreview = computed(
  () => Boolean(store.activePath && store.openFile?.kind === 'text' && isMarkdownFile(store.activePath)),
)
const showMarkdownPreview = computed(() => mdPreview.value && canMarkdownPreview.value && !review.value)

function uriOf(path: string, original = false) {
  return monacoMod!.Uri.from({
    scheme: 'inmemory',
    authority: original ? 'ca-orig' : 'ca',
    path: `/${path}`,
  })
}

function ensureModel(path: string, content: string) {
  if (!monacoMod) return null
  const lang = langOf(path)
  let model = models.get(path)
  if (!model || model.isDisposed()) {
    const existing = monacoMod.editor.getModel(uriOf(path))
    model = existing || monacoMod.editor.createModel(content, lang, uriOf(path))
    model.onDidChangeContent(() => {
      store.updateOpenContent(path, model!.getValue())
    })
    models.set(path, model)
  }
  if (model.getLanguageId() !== lang) monacoMod.editor.setModelLanguage(model, lang)
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
  clearReviewNavigation()
  clearDiffReveal()
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
  editor.updateOptions({ readOnly: Boolean(file.readonly) })
  applySearchReveal(path)
  requestAnimationFrame(() => editor?.layout())
}

function clearSearchDecorations() {
  if (!editor) return
  searchDecorations = editor.deltaDecorations(searchDecorations, [])
}

function applySearchReveal(path: string) {
  if (!editor || !monacoMod) return
  const reveal = store.pendingReveal
  if (reveal?.path === path && reveal.query?.trim()) {
    lastSearchHighlight = {
      path,
      line: Math.max(1, reveal.line),
      query: reveal.query.trim(),
      caseSensitive: reveal.caseSensitive,
    }
  }
  const spec = reveal?.path === path && reveal.query?.trim()
    ? { ...reveal, query: reveal.query.trim(), line: Math.max(1, reveal.line) }
    : lastSearchHighlight?.path === path
      ? lastSearchHighlight
      : null

  if (reveal?.path === path && !spec?.query) {
    const line = Math.max(1, reveal.line)
    clearSearchDecorations()
    editor.revealLineInCenter(line)
    editor.setPosition({ lineNumber: line, column: 1 })
    editor.focus()
    store.pendingReveal = null
    return
  }

  if (!spec?.query) {
    clearSearchDecorations()
    return
  }

  const model = editor.getModel()
  if (!model) return
  const matches = model.findMatches(spec.query, true, false, Boolean(spec.caseSensitive), null, false)
  const current = matches.find((m) => m.range.startLineNumber === spec.line) || matches[0]
  searchDecorations = editor.deltaDecorations(
    searchDecorations,
    matches.map((m) => {
      const isCurrent =
        !!current &&
        m.range.startLineNumber === current.range.startLineNumber &&
        m.range.startColumn === current.range.startColumn
      return {
        range: m.range,
        options: {
          className: isCurrent ? 'ca-search-current' : 'ca-search-match',
          stickiness: monacoMod!.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
          overviewRuler: {
            color: isCurrent ? '#7c9cff' : '#d7ba7d',
            position: monacoMod!.editor.OverviewRulerLane.Center,
          },
        },
      }
    }),
  )

  if (reveal?.path === path) {
    if (current) {
      editor.setSelection(current.range)
      editor.revealRangeInCenter(current.range)
    } else {
      editor.revealLineInCenter(spec.line)
      editor.setPosition({ lineNumber: spec.line, column: 1 })
    }
    editor.focus()
    store.pendingReveal = null
  }
}

function clearReviewNavigation() {
  for (const disposable of reviewNavDisposables) disposable.dispose()
  reviewNavDisposables = []
}

function bindReviewNavigation() {
  clearReviewNavigation()
  if (!monacoMod || !diffEditor) return
  const path = store.activePath
  const canDiff = store.pendingReviewCount(path) > 1
  const canFile = store.pendingReviewPaths.length > 1
  if (!canDiff && !canFile) return
  const bind = (ed: import('monaco-editor').editor.IStandaloneCodeEditor) => {
    reviewNavDisposables.push(
      ed.onKeyDown((e) => {
        if (canDiff && e.keyCode === monacoMod!.KeyCode.UpArrow) {
          e.preventDefault()
          e.stopPropagation()
          store.cycleFileReview(path!, -1)
        } else if (canDiff && e.keyCode === monacoMod!.KeyCode.DownArrow) {
          e.preventDefault()
          e.stopPropagation()
          store.cycleFileReview(path!, 1)
        } else if (canFile && e.keyCode === monacoMod!.KeyCode.LeftArrow) {
          e.preventDefault()
          e.stopPropagation()
          void store.cycleReviewPath(-1)
        } else if (canFile && e.keyCode === monacoMod!.KeyCode.RightArrow) {
          e.preventDefault()
          e.stopPropagation()
          void store.cycleReviewPath(1)
        }
      }),
    )
  }
  bind(diffEditor.getModifiedEditor())
  bind(diffEditor.getOriginalEditor())
}

function clearDiffReveal() {
  diffRevealDisposable?.dispose()
  diffRevealDisposable = null
}

function revealDiffPosition() {
  if (!diffEditor) return
  clearDiffReveal()
  diffEditor.revealFirstDiff()
  diffRevealDisposable = diffEditor.onDidUpdateDiff(() => {
    const changes = diffEditor?.getLineChanges()
    if (!changes?.length || !diffEditor) return
    const first = changes[0]
    const modLine = Math.max(1, first.modifiedStartLineNumber)
    const origLine = Math.max(1, first.originalStartLineNumber)
    const mod = diffEditor.getModifiedEditor()
    const orig = diffEditor.getOriginalEditor()
    mod.revealLineInCenter(modLine)
    orig.revealLineInCenter(origLine)
    mod.setPosition({ lineNumber: modLine, column: 1 })
    clearDiffReveal()
  })
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
  bindReviewNavigation()
  revealDiffPosition()
  requestAnimationFrame(() => {
    diffEditor?.layout()
    diffEditor?.revealFirstDiff()
  })
}

async function onEditorSave() {
  if (review.value || showFilePreview.value) return
  const path = store.activePath
  const file = store.openFile
  if (!path || !file || file.readonly) return
  const model = editor?.getModel()
  if (model) store.updateOpenContent(path, model.getValue())
  await store.saveOpenFile()
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
  editor.addCommand(monacoMod.KeyMod.CtrlCmd | monacoMod.KeyCode.KeyS, () => {
    void onEditorSave()
  })
  host.value.addEventListener('copy', onEditorCopy)
  showPath(store.activePath)
  window.addEventListener('ca-theme', onTheme as EventListener)
  window.addEventListener('ca-file-reload', onReload as EventListener)
  window.addEventListener('ca-focus-editor', onFocusEditor as EventListener)
  window.addEventListener('keydown', onReviewKey)
  document.addEventListener('mousedown', onBulkDocClick)
  document.addEventListener('keydown', onBulkKey)
})

function onFocusEditor() {
  showPath(store.activePath)
  scrollActiveTabIntoView(store.activePath)
}

function scrollActiveTabIntoView(path: string | null) {
  if (!path) return
  void nextTick(() => {
    const container = tabsEl.value
    if (!container) return
    for (const el of container.querySelectorAll<HTMLElement>('.ftab')) {
      if (el.dataset.path === path) {
        el.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' })
        break
      }
    }
  })
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable
}

function onReviewKey(e: KeyboardEvent) {
  if (!review.value) return
  if (isEditableTarget(e.target)) return
  if (e.key === 'ArrowUp' && canCycleDiff.value) {
    e.preventDefault()
    cycleDiff(-1)
    return
  }
  if (e.key === 'ArrowDown' && canCycleDiff.value) {
    e.preventDefault()
    cycleDiff(1)
    return
  }
  if (e.key === 'ArrowLeft' && canCycleFile.value) {
    e.preventDefault()
    void cycleFile(-1)
    return
  }
  if (e.key === 'ArrowRight' && canCycleFile.value) {
    e.preventDefault()
    void cycleFile(1)
  }
}

function onTheme() {
  applyEditorTheme()
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

function onEditorCopy() {
  if (!editor || !store.activePath) return
  const sel = editor.getSelection()
  const model = editor.getModel()
  if (!sel || !model || sel.isEmpty()) return
  const text = model.getValueInRange(sel)
  if (!text) return
  store.setEditorCopyContext({
    path: store.activePath,
    text,
    startLine: sel.startLineNumber,
    endLine: sel.endLineNumber,
  })
}

watch(
  () => store.openFiles.length,
  async () => {
    if (!store.activePath || !monacoMod) return
    await nextTick()
    showPath(store.activePath)
  },
)

watch(
  () =>
    [
      store.activePath,
      review.value?.blockId,
      review.value?.status,
      store.activeReviewIndexFor(store.activePath),
      htmlPreview.value,
    ] as const,
  async () => {
    await nextTick()
    showPath(store.activePath)
  },
)

watch(
  () => store.pendingReveal,
  (reveal) => {
    if (!reveal || !editor) return
    if (store.activePath !== reveal.path) return
    applySearchReveal(reveal.path)
  },
)

watch(
  () => store.activePath,
  (path, prev) => {
    scrollActiveTabIntoView(path)
    if (!path || !prev || !isMarkdownFile(path) || !isMarkdownFile(prev)) mdPreview.value = false
    // Reset HTML to source when switching between different HTML files / leaving HTML
    const nextHtml = path ? /\.(html?|HTML?)$/.test(path) : false
    const prevHtml = prev ? /\.(html?|HTML?)$/.test(prev) : false
    if (!nextHtml || !prevHtml || path !== prev) htmlPreview.value = false
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
  host.value?.removeEventListener('copy', onEditorCopy)
  window.removeEventListener('ca-theme', onTheme as EventListener)
  window.removeEventListener('ca-file-reload', onReload as EventListener)
  window.removeEventListener('ca-focus-editor', onFocusEditor as EventListener)
  window.removeEventListener('keydown', onReviewKey)
  document.removeEventListener('mousedown', onBulkDocClick)
  document.removeEventListener('keydown', onBulkKey)
  for (const model of models.values()) model.dispose()
  for (const model of origModels.values()) model.dispose()
  models.clear()
  origModels.clear()
  diffEditor?.dispose()
  clearReviewNavigation()
  clearDiffReveal()
  editor?.dispose()
})

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
      <div ref="tabsEl" class="tabs" role="tablist" @wheel="onTabWheel">
        <div
          v-for="file in store.openFiles"
          :key="file.path"
          role="tab"
          class="ftab"
          :data-path="file.path"
          :class="{ active: store.activePath === file.path }"
          :title="file.path"
          :aria-selected="store.activePath === file.path"
          tabindex="0"
          @click="store.activateFile(file.path)"
          @keydown.enter.prevent="store.activateFile(file.path)"
          @auxclick="onTabAux(file.path, $event)"
          @contextmenu="onTabContext(file.path, $event)"
        >
          <FileTreeIcon kind="file" :path="file.path" :size="16" />
          <span class="name">{{ fileName(file.path) }}{{ file.dirty ? ' •' : '' }}</span>
          <span v-if="store.pendingReviewCount(file.path)" class="mark">diff</span>
          <button type="button" class="ghost-icon-btn ftab-close" title="关闭" @click.stop="store.closeFile(file.path)">
            <AppIcon name="close" :size="12" :stroke-width="1.75" />
          </button>
        </div>
      </div>
      <div v-if="canMarkdownPreview" class="md-toggle" role="group" aria-label="Markdown 预览">
        <button type="button" class="md-toggle-btn" :class="{ 'is-on': !mdPreview }" @click="mdPreview = false">Markdown</button>
        <button type="button" class="md-toggle-btn" :class="{ 'is-on': mdPreview }" @click="mdPreview = true">预览</button>
      </div>
      <div v-if="canHtmlPreview" class="md-toggle" role="group" aria-label="HTML 预览">
        <button type="button" class="md-toggle-btn" :class="{ 'is-on': !htmlPreview }" @click="htmlPreview = false">源码</button>
        <button type="button" class="md-toggle-btn" :class="{ 'is-on': htmlPreview }" @click="htmlPreview = true">预览</button>
      </div>
    </header>
    <div v-if="store.fileNotice" class="file-notice" role="status">
      <span>{{ store.fileNotice }}</span>
      <button type="button" class="ghost-icon-btn notice-x" @click="store.clearFileNotice()">
        <AppIcon name="close" :size="14" :stroke-width="1.75" />
      </button>
    </div>
    <div v-if="pendingCount" class="review-bar">
      <div class="review-nav" role="navigation" :aria-label="t('editor.reviewNav')">
        <div class="review-nav-group">
          <button
            type="button"
            class="nav-btn"
            :disabled="!canCycleDiff"
            :title="t('editor.prevDiff')"
            @click="cycleDiff(-1)"
          >
            <AppIcon name="chevron-up" :size="16" :stroke-width="1.75" />
          </button>
          <span class="nav-label">{{ t('editor.diffNav', { i: fileReviewIndex, n: Math.max(fileReviewCount, 1) }) }}</span>
          <button
            type="button"
            class="nav-btn"
            :disabled="!canCycleDiff"
            :title="t('editor.nextDiff')"
            @click="cycleDiff(1)"
          >
            <AppIcon name="chevron-down" :size="16" :stroke-width="1.75" />
          </button>
        </div>
        <span class="review-nav-sep" aria-hidden="true" />
        <div class="review-nav-group">
          <button
            type="button"
            class="nav-btn"
            :disabled="!canCycleFile"
            :title="t('editor.prevFile')"
            @click="cycleFile(-1)"
          >
            <AppIcon name="chevron-left" :size="16" :stroke-width="1.75" />
          </button>
          <span class="nav-label nav-label-long">{{ t('editor.fileNav', { i: filePathIndex || 1, n: filePendingPathCount }) }}</span>
          <span class="nav-label nav-label-short">{{ filePathIndex || 1 }}/{{ filePendingPathCount }}</span>
          <button
            type="button"
            class="nav-btn"
            :disabled="!canCycleFile"
            :title="t('editor.nextFile')"
            @click="cycleFile(1)"
          >
            <AppIcon name="chevron-right" :size="16" :stroke-width="1.75" />
          </button>
        </div>
      </div>
      <div class="review-actions">
        <div v-if="review" class="action-group" role="group" :aria-label="t('editor.reviewActionsCurrent')">
          <button
            type="button"
            class="action-btn is-reject"
            :title="t('editor.reject')"
            @click="store.rejectReview(review.path)"
          >
            <AppIcon name="close" :size="16" :stroke-width="1.75" />
            <span class="action-label">{{ t('editor.reject') }}</span>
          </button>
          <button
            type="button"
            class="action-btn is-accept"
            :title="t('editor.accept')"
            @click="store.acceptReview(review.path)"
          >
            <AppIcon name="check" :size="16" :stroke-width="1.75" />
            <span class="action-label">{{ t('editor.accept') }}</span>
          </button>
        </div>
        <div ref="bulkActionRef" class="action-group bulk-group" role="group" :aria-label="t('editor.reviewActionsAll')">
          <button
            type="button"
            class="action-btn is-reject"
            :class="{ 'is-active': bulkConfirm === 'reject' }"
            :title="t('editor.rejectAll')"
            @click="openBulkConfirm('reject')"
          >
            <AppIcon name="close-all" :size="16" :stroke-width="1.75" />
            <span class="action-label">{{ t('editor.rejectAll') }}</span>
          </button>
          <button
            type="button"
            class="action-btn is-accept"
            :class="{ 'is-active': bulkConfirm === 'accept' }"
            :title="t('editor.acceptAll')"
            @click="openBulkConfirm('accept')"
          >
            <AppIcon name="check" :size="16" :stroke-width="1.75" />
            <span class="action-label">{{ t('editor.acceptAll') }}</span>
          </button>
          <div
            v-if="bulkConfirm"
            class="bulk-confirm"
            :class="{ 'is-danger': bulkConfirm === 'reject' }"
            role="dialog"
            :aria-label="bulkConfirm === 'accept' ? t('confirm.acceptAllReviewsTitle') : t('confirm.rejectAllReviewsTitle')"
            @mousedown.stop
          >
            <span class="bulk-confirm-count">{{ pendingCount }}</span>
            <button
              type="button"
              class="ghost-icon-btn bulk-btn"
              :title="t('common.cancel')"
              :aria-label="t('common.cancel')"
              @click="closeBulkConfirm"
            >
              <AppIcon name="close" :size="16" :stroke-width="1.75" />
            </button>
            <button
              type="button"
              class="ghost-icon-btn bulk-btn"
              :class="bulkConfirm === 'reject' ? 'is-danger' : 'is-primary'"
              :title="t('confirm.confirm')"
              :aria-label="t('confirm.confirm')"
              @click="confirmBulk"
            >
              <AppIcon name="check" :size="16" :stroke-width="1.75" />
            </button>
          </div>
        </div>
      </div>
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
  flex-shrink: 0;
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
.ftab:hover { background: transparent; color: var(--text-h); opacity: var(--ghost-hover-opacity); }
.ftab.active {
  background: var(--editor-bg);
  color: var(--text-h);
  opacity: 1;
  box-shadow: inset 0 -2px 0 var(--primary);
}
.ftab-close {
  opacity: 0;
  transition: opacity 0.15s ease;
}
.ftab:hover .ftab-close,
.ftab.active .ftab-close {
  opacity: var(--ghost-hover-opacity);
}
.ftab-close:hover {
  opacity: 1 !important;
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
  height: var(--ghost-btn-height);
  padding: 0;
  border: 0;
  border-radius: var(--ghost-btn-radius);
  background: transparent;
  flex-shrink: 0;
  gap: 2px;
}
.md-toggle-btn {
  height: var(--ghost-btn-height);
  padding: 0 8px;
  border: none;
  border-radius: var(--ghost-btn-radius);
  background: transparent;
  color: var(--text-h);
  font: inherit;
  font-size: var(--ghost-btn-font-size);
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition: opacity 0.15s ease;
}
.md-toggle-btn:hover {
  opacity: var(--ghost-hover-opacity);
}
.md-toggle-btn.is-on {
  background: transparent;
  color: var(--primary);
  opacity: 1;
}
.review-bar {
  container-type: inline-size;
  container-name: review-bar;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 36px;
  padding: 6px 8px;
  border-bottom: var(--border-width) solid var(--border);
  background: color-mix(in srgb, var(--primary) 8%, var(--bg));
  color: var(--text);
  font-size: 12.5px;
  overflow: visible;
}
.review-nav {
  display: inline-flex;
  align-items: stretch;
  flex-shrink: 1;
  min-width: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  overflow: visible;
  box-shadow: none;
}
.review-nav-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px;
}
.review-nav-sep {
  width: 1px;
  align-self: stretch;
  background: var(--border);
  flex-shrink: 0;
}
.nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: auto;
  min-width: var(--ghost-btn-height);
  height: var(--ghost-btn-height);
  padding: var(--ghost-btn-padding);
  border: 0;
  border-radius: var(--ghost-btn-radius);
  background: transparent;
  color: var(--text-h);
  cursor: pointer;
  flex-shrink: 0;
  transition: opacity 0.15s ease;
}
.nav-btn:hover:not(:disabled) {
  background: transparent;
  opacity: var(--ghost-hover-opacity);
}
.nav-btn:disabled {
  opacity: 0.28;
  cursor: default;
}
.nav-label {
  min-width: 0;
  padding: 0 2px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-h);
  text-align: center;
  white-space: nowrap;
  user-select: none;
}
.nav-label-short {
  display: none;
  min-width: 36px;
}
.nav-label-long {
  min-width: 72px;
}
.review-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  flex-shrink: 0;
  overflow: visible;
}
.action-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
.bulk-group {
  position: relative;
  overflow: visible;
}
.action-btn.is-active {
  opacity: var(--ghost-hover-opacity);
}
.action-btn.is-active.is-accept {
  color: var(--primary);
  opacity: 1;
}
.bulk-confirm {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 6px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: var(--dropdown-shadow);
}
.bulk-confirm::before {
  display: none;
}
.bulk-confirm.is-danger {
  border-color: color-mix(in srgb, var(--danger) 28%, var(--border));
}
.bulk-confirm-count {
  min-width: 14px;
  padding: 0 4px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  color: var(--text-secondary);
  text-align: center;
}
.bulk-btn.is-primary {
  color: var(--primary);
}
.bulk-btn.is-danger {
  color: var(--danger);
}
.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: var(--ghost-btn-height);
  padding: 0 6px;
  border: 0;
  border-radius: var(--ghost-btn-radius);
  background: transparent;
  color: var(--text-h);
  font: inherit;
  font-size: var(--ghost-btn-font-size);
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition: opacity 0.15s ease, color 0.12s ease;
}
.action-btn:hover {
  background: transparent;
  opacity: var(--ghost-hover-opacity);
}
.action-btn.is-reject:hover {
  background: transparent;
  color: var(--danger);
  opacity: 1;
}
.action-btn.is-accept {
  color: var(--primary);
}
.action-btn.is-accept:hover {
  background: transparent;
  color: var(--primary);
  opacity: var(--ghost-hover-opacity);
}
.action-btn.is-strong {
  color: var(--primary);
  opacity: 1;
}
.action-btn.is-strong:hover {
  background: transparent;
  opacity: var(--ghost-hover-opacity);
}
@container review-bar (max-width: 640px) {
  .action-label {
    display: none;
  }
  .action-btn {
    width: 28px;
    padding: 0;
  }
  .nav-label-long {
    display: none;
  }
  .nav-label-short {
    display: inline;
  }
}
@container review-bar (max-width: 480px) {
  .review-bar {
    align-items: stretch;
  }
  .review-nav {
    flex: 1 1 auto;
    justify-content: center;
  }
  .review-actions {
    width: 100%;
    margin-left: 0;
    justify-content: flex-end;
  }
}
@container review-bar (max-width: 360px) {
  .review-nav-group {
    padding: 2px;
  }
  .nav-label {
    font-size: 11px;
  }
  .nav-label-short {
    min-width: 28px;
  }
  .action-group {
    flex: 1;
    justify-content: center;
  }
}
.spacer { flex: 1; }
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

<style>
.ca-search-match {
  background: color-mix(in srgb, var(--primary) 22%, transparent);
}
.ca-search-current {
  background: color-mix(in srgb, var(--primary) 42%, transparent);
  box-shadow: inset 0 -1px 0 color-mix(in srgb, var(--primary) 55%, transparent);
}
</style>
