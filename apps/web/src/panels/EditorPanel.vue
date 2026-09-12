<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { currentTheme } from '@/theme'
import FileTreeIcon from '@/components/FileTreeIcon.vue'
import AppIcon from '@/components/AppIcon.vue'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import ContextMenu, { type ContextMenuItem } from '@/components/ContextMenu.vue'
import InlineEditWidget from '@/components/InlineEditWidget.vue'
import InlineEditChip from '@/components/InlineEditChip.vue'
import GotoPeek, { type GotoHit } from '@/components/GotoPeek.vue'
import FilePreviewHost from '@/preview/FilePreviewHost.vue'
import { isPreviewKind } from '@/preview/classify'
import { langOf } from '@/utils/editorLang'
import { canFormatPath, formatDocumentText } from '@/utils/formatDocument'
import { expandInlineRange, findLocalDefinitions, identifierAt } from '@/utils/gotoSymbol'
import { isRunnableScript, isWindowsRoot, scriptRunCommand } from '@/utils/scriptRun'
import { api } from '@/api/http'
import { useToast } from '@/composables/useToast'
import { t } from '@/i18n'

const store = useAppStore()
const toast = useToast()
const host = ref<HTMLDivElement | null>(null)
const wrapEl = ref<HTMLDivElement | null>(null)
const tabsEl = ref<HTMLElement | null>(null)
const diffHost = ref<HTMLDivElement | null>(null)
const mdPreview = ref(false)
/** HTML: true = iframe preview, false = Monaco source */
const htmlPreview = ref(false)
const tabMenu = ref<{ x: number; y: number; path: string } | null>(null)
const editorMenu = ref<{ x: number; y: number } | null>(null)
const secondaryHost = ref<HTMLDivElement | null>(null)
const dragTabPath = ref<string | null>(null)
const dropTabPath = ref<string | null>(null)
/** none | right (side-by-side) | down (stacked) */
const splitMode = ref<'none' | 'right' | 'down'>('none')
const focusedPane = ref<'primary' | 'secondary'>('primary')
const secondaryPath = ref<string | null>(null)
const primaryPath = ref<string | null>(null)
let editorCtxDisposable: import('monaco-editor').IDisposable | null = null
let editor: import('monaco-editor').editor.IStandaloneCodeEditor | null = null
let secondaryEditor: import('monaco-editor').editor.IStandaloneCodeEditor | null = null
let diffEditor: import('monaco-editor').editor.IStandaloneDiffEditor | null = null
let monacoMod: typeof import('monaco-editor') | null = null
let reviewNavDisposables: import('monaco-editor').IDisposable[] = []
let diffRevealDisposable: import('monaco-editor').IDisposable | null = null
let hunkDiffDisposable: import('monaco-editor').IDisposable | null = null
let hunkZoneIdsMod: string[] = []
let hunkZoneIdsOrig: string[] = []
let hunkWidgets: import('monaco-editor').editor.IContentWidget[] = []
const models = new Map<string, import('monaco-editor').editor.ITextModel>()
const origModels = new Map<string, import('monaco-editor').editor.ITextModel>()
let searchDecorations: string[] = []
let lastSearchHighlight: { path: string; line: number; query: string; caseSensitive?: boolean } | null = null
let editorInputDisposables: import('monaco-editor').IDisposable[] = []
let inlineDecorations: string[] = []
let inlinePreviewApplied = false
let inlineGen = 0
const inlineOpen = ref(false)
const inlinePhase = ref<'prompt' | 'loading' | 'diff'>('prompt')
const inlineInstruction = ref('')
const inlineOriginal = ref('')
const inlineReplacement = ref('')
const inlineError = ref('')
const inlineLeft = ref(16)
const inlineTop = ref(16)
const inlineLineLabel = ref('')
const gotoOpen = ref(false)
const gotoHits = ref<GotoHit[]>([])
const gotoActive = ref(0)
const gotoLeft = ref(16)
const gotoTop = ref(16)
const gotoSymbolName = ref('')
const chipOpen = ref(false)
const chipLeft = ref(16)
const chipTop = ref(16)
let skipSelectionChip = false
let chipTimer = 0
let chipEditor: import('monaco-editor').editor.IStandaloneCodeEditor | null = null
let gotoModHeld = false
let gotoHoverEd: import('monaco-editor').editor.IStandaloneCodeEditor | null = null
let gotoHoverDecorations: string[] = []
let lastGotoMouse: {
  ed: import('monaco-editor').editor.IStandaloneCodeEditor
  position: { lineNumber: number; column: number }
} | null = null
const review = computed(() => store.pendingReview(store.activePath))
const gitDiff = computed(() => {
  const path = store.activePath
  if (!path || review.value) return null
  return store.gitEditorDiff[path] || null
})
const showingDiff = computed(() => Boolean(review.value || gitDiff.value))
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
const canCycleChange = computed(() => canCycleDiff.value || canCycleFile.value)

function cycleDiff(delta: number) {
  const path = store.activePath
  if (!path) return
  if (canCycleDiff.value) {
    store.cycleFileReview(path, delta)
    return
  }
  if (canCycleFile.value) void cycleFile(delta)
}

async function cycleFile(delta: number) {
  if (!canCycleFile.value) return
  await store.cycleReviewPath(delta)
}

const isHtmlFile = computed(() => store.openFile?.kind === 'html')
const canHtmlPreview = computed(() => Boolean(isHtmlFile.value && !review.value && !gitDiff.value))
const showHtmlPreview = computed(() => htmlPreview.value && canHtmlPreview.value)

const activeIsBinaryPreview = computed(() => {
  const f = store.openFile
  return Boolean(f && isPreviewKind(f.kind) && f.kind !== 'html')
})

const showFilePreview = computed(() => activeIsBinaryPreview.value || showHtmlPreview.value)
const runningScript = ref(false)
const canRunScript = computed(() => {
  const path = store.activePath
  const file = store.openFile
  if (!path || !file || file.readonly || showingDiff.value || showFilePreview.value) return false
  return isRunnableScript(path)
})

async function runActiveScript(path = store.activePath) {
  if (!path || runningScript.value) return
  const command = scriptRunCommand(path, { windows: isWindowsRoot(store.workspace?.root_path) })
  if (!command) {
    toast.error(t('editor.runNotSupported'))
    return
  }
  runningScript.value = true
  try {
    if (path !== store.activePath) store.activateFile(path)
    await nextTick()
    if (store.openFile?.path === path && store.openFile.dirty) await onEditorSave()
    window.dispatchEvent(new CustomEvent('ca-run-in-terminal', {
      detail: { command, cwd: store.parentPath(path) },
    }))
  } catch (err) {
    toast.error(err instanceof Error ? err.message : t('common.saveFailed'))
  } finally {
    runningScript.value = false
  }
}

function onRunFileEvent() {
  void runActiveScript()
}

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
  const bg = cssColor('--editor-bg', dark ? '#121218' : '#ffffff')
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

/** Primary pane file (stable when secondary pane is focused). */
const primaryFile = computed(() => {
  const path =
    splitMode.value === 'none' ? store.activePath : primaryPath.value || store.activePath
  return path ? store.openFiles.find((f) => f.path === path) ?? null : null
})
const primaryCanHtmlPreview = computed(() => Boolean(primaryFile.value?.kind === 'html' && !review.value && !gitDiff.value))
const primaryShowHtmlPreview = computed(() => htmlPreview.value && primaryCanHtmlPreview.value)
const primaryShowFilePreview = computed(() => {
  const f = primaryFile.value
  if (!f) return false
  if (isPreviewKind(f.kind) && f.kind !== 'html') return true
  return primaryShowHtmlPreview.value
})
const primaryShowMarkdownPreview = computed(() => {
  const f = primaryFile.value
  return Boolean(
    mdPreview.value && f && f.kind === 'text' && isMarkdownFile(f.path) && !review.value && !gitDiff.value,
  )
})

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
  scrollbar: { verticalScrollbarSize: 6, horizontalScrollbarSize: 6 },
  contextmenu: false,
  multiCursorModifier: 'alt' as const,
}

function detachModelExcept(
  model: import('monaco-editor').editor.ITextModel,
  keep: import('monaco-editor').editor.IStandaloneCodeEditor | null,
) {
  if (editor && editor !== keep && editor.getModel() === model) editor.setModel(null)
  if (secondaryEditor && secondaryEditor !== keep && secondaryEditor.getModel() === model) {
    secondaryEditor.setModel(null)
  }
}

function showPathOn(
  ed: import('monaco-editor').editor.IStandaloneCodeEditor | null,
  path: string | null,
  opts?: { allowReview?: boolean },
) {
  if (!monacoMod || !ed) return
  if (opts?.allowReview && review.value && path) {
    showDiff(path, review.value.before, review.value.after, { readOnly: true })
    return
  }
  const file = path ? store.openFiles.find((f) => f.path === path) : null
  if (!path || !file) {
    ed.setModel(null)
    return
  }
  if (isPreviewKind(file.kind) && (file.kind !== 'html' || htmlPreview.value)) {
    ed.setModel(null)
    return
  }
  const model = ensureModel(path, file.content ?? '')
  if (!model) return
  detachModelExcept(model, ed)
  ed.setModel(model)
  ed.updateOptions({ readOnly: Boolean(file.readonly) })
  bindEditorContextMenu(ed)
  if (ed === editor) applySearchReveal(path)
  requestAnimationFrame(() => ed.layout())
}

function showPath(path: string | null) {
  if (!monacoMod) return
  if (review.value && path) {
    showDiff(path, review.value.before, review.value.after, { readOnly: true })
    return
  }
  const file = path ? store.openFiles.find((f) => f.path === path) : null
  const gd = path ? store.gitEditorDiff[path] : null
  if (gd && path && file && !(isPreviewKind(file.kind) && file.kind !== 'html')) {
    showDiff(path, gd.original, file.content ?? '', {
      readOnly: Boolean(gd.modifiedReadonly || file.readonly),
    })
    return
  }
  diffEditor?.setModel(null)
  clearReviewNavigation()
  clearDiffReveal()
  if (splitMode.value !== 'none' && focusedPane.value === 'secondary') {
    secondaryPath.value = path
    showPathOn(secondaryEditor, path)
    return
  }
  primaryPath.value = path
  showPathOn(editor, path, { allowReview: true })
}

function panePath(pane: 'primary' | 'secondary') {
  if (pane === 'secondary') return secondaryPath.value
  return primaryPath.value ?? store.activePath
}

function focusPane(pane: 'primary' | 'secondary') {
  if (splitMode.value === 'none' && pane === 'secondary') return
  focusedPane.value = pane
  const path = panePath(pane)
  if (path && store.activePath !== path) store.activateFile(path)
  else if (path) showPath(path)
  const ed = pane === 'secondary' ? secondaryEditor : editor
  ed?.focus()
}

function activateTab(path: string) {
  if (splitMode.value !== 'none' && focusedPane.value === 'secondary') {
    secondaryPath.value = path
    focusedPane.value = 'secondary'
    store.activateFile(path)
    showPathOn(secondaryEditor, path)
    return
  }
  focusedPane.value = 'primary'
  primaryPath.value = path
  store.activateFile(path)
}

/** Double-click tab: force explorer locate even if already active. */
function onTabDblClick(path: string) {
  activateTab(path)
  window.dispatchEvent(new CustomEvent('ca-reveal-in-tree', { detail: { path } }))
}

async function ensureSecondaryEditor() {
  if (!monacoMod || secondaryEditor || !secondaryHost.value) return
  secondaryEditor = monacoMod.editor.create(secondaryHost.value, {
    value: '',
    language: 'plaintext',
    theme: 'ca-editor',
    ...editorOptions,
  })
  bindEditorContextMenu(secondaryEditor)
  bindEditorCommands(secondaryEditor)
  secondaryEditor.onDidFocusEditorText(() => {
    focusedPane.value = 'secondary'
    if (secondaryPath.value) store.activateFile(secondaryPath.value)
  })
}

function disposeSecondaryEditor() {
  if (secondaryEditor) {
    const model = secondaryEditor.getModel()
    secondaryEditor.setModel(null)
    secondaryEditor.dispose()
    secondaryEditor = null
    void model
  }
}

async function splitEditor(mode: 'right' | 'down', seedPath?: string) {
  if (review.value || gitDiff.value) return
  const current = store.activePath
  primaryPath.value = current
  const seed =
    seedPath ||
    store.openFiles.find((f) => f.path !== current)?.path ||
    current
  secondaryPath.value = seed || null
  splitMode.value = mode
  focusedPane.value = 'secondary'
  await nextTick()
  await ensureSecondaryEditor()
  showPathOn(editor, primaryPath.value)
  showPathOn(secondaryEditor, secondaryPath.value)
  if (secondaryPath.value) store.activateFile(secondaryPath.value)
  requestAnimationFrame(() => {
    editor?.layout()
    secondaryEditor?.layout()
  })
}

function closeSplit(keep: 'primary' | 'secondary' = 'primary') {
  if (splitMode.value === 'none') return
  const keepPath = keep === 'secondary' ? secondaryPath.value : primaryPath.value
  disposeSecondaryEditor()
  splitMode.value = 'none'
  focusedPane.value = 'primary'
  secondaryPath.value = null
  primaryPath.value = keepPath
  if (keepPath) store.activateFile(keepPath)
  showPathOn(editor, keepPath)
  requestAnimationFrame(() => editor?.layout())
}

function onTabDragStart(path: string, e: DragEvent) {
  dragTabPath.value = path
  dropTabPath.value = null
  e.dataTransfer?.setData('text/plain', path)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

function onTabDragOver(path: string, e: DragEvent) {
  if (!dragTabPath.value || dragTabPath.value === path) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  dropTabPath.value = path
}

function onTabDragLeave(path: string) {
  if (dropTabPath.value === path) dropTabPath.value = null
}

function onTabDrop(path: string, e: DragEvent) {
  e.preventDefault()
  const fromPath = dragTabPath.value || e.dataTransfer?.getData('text/plain')
  dragTabPath.value = null
  dropTabPath.value = null
  if (!fromPath || fromPath === path) return
  const from = store.openFiles.findIndex((f) => f.path === fromPath)
  const to = store.openFiles.findIndex((f) => f.path === path)
  if (from < 0 || to < 0) return
  store.reorderOpenFiles(from, to)
}

function onTabDragEnd() {
  dragTabPath.value = null
  dropTabPath.value = null
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
    skipSelectionChip = true
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
  const bind = (ed: import('monaco-editor').editor.IStandaloneCodeEditor) => {
    reviewNavDisposables.push(
      ed.onKeyDown((e) => {
        const path = store.activePath
        const canDiff = store.pendingReviewCount(path) > 1
        const canFile = store.pendingReviewPaths.length > 1
        if (!canDiff && !canFile) return
        if (e.keyCode === monacoMod!.KeyCode.UpArrow) {
          e.preventDefault()
          e.stopPropagation()
          if (canDiff && path) store.cycleFileReview(path, -1)
          else void store.cycleReviewPath(-1)
        } else if (e.keyCode === monacoMod!.KeyCode.DownArrow) {
          e.preventDefault()
          e.stopPropagation()
          if (canDiff && path) store.cycleFileReview(path, 1)
          else void store.cycleReviewPath(1)
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

function currentLineChange() {
  const changes = diffEditor?.getLineChanges()
  if (!changes?.length || !diffEditor) return null
  const line = diffEditor.getModifiedEditor().getPosition()?.lineNumber ?? 1
  for (const change of changes) {
    const start = change.modifiedStartLineNumber || 1
    const end = change.modifiedEndLineNumber || start
    if (line >= Math.min(start, end) && line <= Math.max(start, end)) return change
  }
  // Prefer nearest change at/after cursor, else first
  return changes.find((c) => (c.modifiedStartLineNumber || 1) >= line) || changes[0]
}

function clearHunkWidgets() {
  if (diffEditor) {
    const mod = diffEditor.getModifiedEditor()
    const orig = diffEditor.getOriginalEditor()
    for (const widget of hunkWidgets) mod.removeContentWidget(widget)
    if (hunkZoneIdsMod.length) {
      mod.changeViewZones((accessor) => {
        for (const id of hunkZoneIdsMod) accessor.removeZone(id)
      })
    }
    if (hunkZoneIdsOrig.length) {
      orig.changeViewZones((accessor) => {
        for (const id of hunkZoneIdsOrig) accessor.removeZone(id)
      })
    }
  }
  hunkWidgets = []
  hunkZoneIdsMod = []
  hunkZoneIdsOrig = []
}

function bindHunkPointer(el: HTMLElement, onClick: () => void) {
  const stop = (e: Event) => {
    e.preventDefault()
    e.stopPropagation()
  }
  el.addEventListener('pointerdown', stop, true)
  el.addEventListener('mousedown', stop, true)
  el.addEventListener('pointerup', (e) => {
    stop(e)
    onClick()
  }, true)
}

function makeHunkButton(label: string, kind: 'accept' | 'reject', onClick: () => void) {
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.className = `ca-hunk-btn is-${kind}`
  btn.textContent = label
  bindHunkPointer(btn, onClick)
  return btn
}

function makeHunkNavButton(dir: 'up' | 'down', title: string, disabled: boolean, onClick: () => void) {
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.className = 'ca-hunk-btn is-nav'
  btn.title = title
  btn.disabled = disabled
  const path = dir === 'up' ? 'M18 15l-6-6-6 6' : 'M6 9l6 6 6-6'
  btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="${path}"/></svg>`
  if (!disabled) bindHunkPointer(btn, onClick)
  return btn
}

function revealHunkAt(index: number) {
  const changes = diffEditor?.getLineChanges()
  if (!changes?.length || !diffEditor) return
  const i = ((index % changes.length) + changes.length) % changes.length
  const change = changes[i]
  const modLine = Math.max(1, change.modifiedStartLineNumber)
  const origLine = Math.max(1, change.originalStartLineNumber)
  const mod = diffEditor.getModifiedEditor()
  const orig = diffEditor.getOriginalEditor()
  mod.revealLineInCenter(modLine)
  orig.revealLineInCenter(origLine)
  mod.setPosition({ lineNumber: modLine, column: 1 })
  mod.focus()
}

function syncHunkWidgets() {
  clearHunkWidgets()
  if (!monacoMod || !diffEditor || !review.value) return
  const changes = diffEditor.getLineChanges()
  if (!changes?.length) return
  const path = review.value.path
  const blockId = review.value.blockId
  const mod = diffEditor.getModifiedEditor()
  const orig = diffEditor.getOriginalEditor()
  const Above = monacoMod.editor.ContentWidgetPositionPreference.ABOVE
  const total = changes.length
  mod.changeViewZones((modAcc) => {
    orig.changeViewZones((origAcc) => {
      changes.forEach((change, index) => {
        const snap = {
          originalStartLineNumber: change.originalStartLineNumber,
          originalEndLineNumber: change.originalEndLineNumber,
          modifiedStartLineNumber: change.modifiedStartLineNumber,
          modifiedEndLineNumber: change.modifiedEndLineNumber,
        }
        const modStart = snap.modifiedStartLineNumber > 0 ? snap.modifiedStartLineNumber : 1
        const origStart = snap.originalStartLineNumber > 0 ? snap.originalStartLineNumber : 1
        hunkZoneIdsMod.push(
          modAcc.addZone({
            afterLineNumber: Math.max(0, modStart - 1),
            heightInPx: 36,
            domNode: document.createElement('div'),
          }),
        )
        hunkZoneIdsOrig.push(
          origAcc.addZone({
            afterLineNumber: Math.max(0, origStart - 1),
            heightInPx: 36,
            domNode: document.createElement('div'),
          }),
        )
        const node = document.createElement('div')
        node.className = 'ca-hunk-actions'
        const nav = document.createElement('span')
        nav.className = 'ca-hunk-nav'
        const indexEl = document.createElement('span')
        indexEl.className = 'ca-hunk-index'
        indexEl.textContent = `${index + 1}/${total}`
        const canSwitch = total > 1
        nav.append(
          makeHunkNavButton('up', t('editor.prevDiff'), !canSwitch, () => revealHunkAt(index - 1)),
          indexEl,
          makeHunkNavButton('down', t('editor.nextDiff'), !canSwitch, () => revealHunkAt(index + 1)),
        )
        node.append(
          nav,
          makeHunkButton(t('editor.reject'), 'reject', () => {
            void store.rejectReviewHunk(path, snap, blockId)
          }),
          makeHunkButton(t('editor.accept'), 'accept', () => {
            void store.acceptReviewHunk(path, snap, blockId)
          }),
        )
        const widget: import('monaco-editor').editor.IContentWidget = {
          getId: () => `ca-hunk-actions-${index}`,
          getDomNode: () => node,
          allowEditorOverflow: true,
          getPosition: () => ({
            position: { lineNumber: Math.max(1, modStart), column: 1 },
            preference: [Above],
          }),
        }
        mod.addContentWidget(widget)
        hunkWidgets.push(widget)
        mod.layoutContentWidget(widget)
      })
    })
  })
}

function bindHunkWidgets() {
  hunkDiffDisposable?.dispose()
  if (!diffEditor) return
  hunkDiffDisposable = diffEditor.onDidUpdateDiff(() => {
    const current = review.value
    if (!current) {
      clearHunkWidgets()
      return
    }
    const changes = diffEditor?.getLineChanges()
    if (changes && changes.length === 0) {
      clearHunkWidgets()
      void store.acceptReview(current.path, current.blockId)
      return
    }
    syncHunkWidgets()
  })
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

function showDiff(path: string, before: string, after: string, opts?: { readOnly?: boolean }) {
  if (!monacoMod || !diffHost.value) return
  const readOnly = opts?.readOnly !== false
  if (!diffEditor) {
    diffEditor = monacoMod.editor.createDiffEditor(diffHost.value, {
      ...editorOptions,
      theme: 'ca-editor',
      readOnly,
      originalEditable: false,
      renderSideBySide: true,
      ignoreTrimWhitespace: false,
    })
    bindEditorContextMenu(diffEditor.getModifiedEditor())
    bindEditorCommands(diffEditor.getModifiedEditor())
    bindHunkWidgets()
  } else {
    diffEditor.updateOptions({ readOnly })
  }
  const original = ensureOrigModel(path, before)
  const modified = ensureModel(path, after)
  if (original && modified) diffEditor.setModel({ original, modified })
  if (readOnly) bindReviewNavigation()
  else clearReviewNavigation()
  if (review.value) syncHunkWidgets()
  else clearHunkWidgets()
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
  if (!store.settings) await store.loadSettings()
  const formatOnSave = store.settings?.values?.['ui.format_on_save'] !== false
  if (formatOnSave) await formatActiveDocument()
  const ed = activeEditor()
  const model = ed?.getModel()
  if (model) store.updateOpenContent(path, model.getValue())
  await store.saveOpenFile()
}

function onEditorSaveEvent(e: Event) {
  const notify = Boolean((e as CustomEvent<{ notify?: boolean }>).detail?.notify)
  void onEditorSave()
    .then(() => {
      if (notify) toast.success(t('common.saved'))
    })
    .catch((err) => {
      toast.error(err instanceof Error ? err.message : t('common.saveFailed'))
    })
}

function onInlineEditEvent() {
  openInlineEdit()
}

function onGotoEvent() {
  void gotoDefinition()
}

function bindEditorCommands(ed: import('monaco-editor').editor.IStandaloneCodeEditor) {
  if (!monacoMod) return
  ed.addCommand(monacoMod.KeyMod.CtrlCmd | monacoMod.KeyCode.KeyS, () => {
    void onEditorSave()
  })
  ed.addCommand(monacoMod.KeyMod.Shift | monacoMod.KeyMod.Alt | monacoMod.KeyCode.KeyF, () => {
    void formatActiveDocument()
  })
  ed.addCommand(monacoMod.KeyCode.F12, () => {
    void gotoDefinition()
  })
  ed.addCommand(monacoMod.KeyCode.F5, () => {
    void runActiveScript()
  })
  editorInputDisposables.push(
    ed.onKeyDown((e) => {
      if (
        e.keyCode === monacoMod!.KeyCode.KeyK &&
        (e.ctrlKey || e.metaKey) &&
        !e.altKey &&
        !e.shiftKey
      ) {
        e.preventDefault()
        e.stopPropagation()
        openInlineEdit()
      }
    }),
  )
  editorInputDisposables.push(
    ed.onMouseDown((e) => {
      if (!(e.event.ctrlKey || e.event.metaKey) || e.event.altKey || e.event.shiftKey) return
      if (!monacoMod) return
      if (e.target.type !== monacoMod.editor.MouseTargetType.CONTENT_TEXT) return
      const pos = e.target.position
      if (!pos) return
      e.event.preventDefault()
      void gotoDefinitionAt(pos)
    }),
  )
  editorInputDisposables.push(
    ed.onDidChangeCursorSelection(() => {
      scheduleInlineChip(ed)
    }),
  )
  editorInputDisposables.push(
    ed.onDidScrollChange(() => {
      if (chipOpen.value && chipEditor === ed) placeInlineChip(ed)
      if (gotoModHeld && lastGotoMouse?.ed === ed) applyGotoHover(ed, lastGotoMouse.position)
    }),
  )
  editorInputDisposables.push(
    ed.onMouseMove((e) => {
      const pos = e.target.position
      if (!pos || !monacoMod) {
        if (gotoModHeld) clearGotoHover()
        return
      }
      lastGotoMouse = { ed, position: pos }
      if (!gotoModHeld) return
      if (e.target.type !== monacoMod.editor.MouseTargetType.CONTENT_TEXT) {
        clearGotoHover()
        return
      }
      applyGotoHover(ed, pos)
    }),
  )
  editorInputDisposables.push(
    ed.onMouseLeave(() => {
      if (lastGotoMouse?.ed === ed) lastGotoMouse = null
      if (gotoHoverEd === ed) clearGotoHover()
    }),
  )
}

function hideInlineChip() {
  if (chipTimer) {
    window.clearTimeout(chipTimer)
    chipTimer = 0
  }
  chipOpen.value = false
  chipEditor = null
}

function placeInlineChip(ed: import('monaco-editor').editor.IStandaloneCodeEditor) {
  const sel = ed.getSelection()
  if (!sel || sel.isEmpty()) {
    hideInlineChip()
    return
  }
  const pos = overlayAt(
    ed,
    { lineNumber: sel.startLineNumber, column: sel.startColumn },
    { above: true },
  )
  chipLeft.value = pos.left
  chipTop.value = pos.top
  chipEditor = ed
  chipOpen.value = true
}

function scheduleInlineChip(ed: import('monaco-editor').editor.IStandaloneCodeEditor) {
  if (skipSelectionChip) {
    skipSelectionChip = false
    hideInlineChip()
    return
  }
  if (chipTimer) {
    window.clearTimeout(chipTimer)
    chipTimer = 0
  }
  if (inlineOpen.value || review.value || editorReadOnly() || gotoOpen.value) {
    hideInlineChip()
    return
  }
  const sel = ed.getSelection()
  const model = ed.getModel()
  if (!sel || sel.isEmpty() || !model) {
    hideInlineChip()
    return
  }
  const text = model.getValueInRange(sel)
  if (!text.trim()) {
    hideInlineChip()
    return
  }
  chipTimer = window.setTimeout(() => {
    chipTimer = 0
    if (inlineOpen.value || review.value || editorReadOnly()) return
    placeInlineChip(ed)
  }, 160)
}

function clearGotoHover() {
  if (gotoHoverEd && gotoHoverDecorations.length) {
    gotoHoverDecorations = gotoHoverEd.deltaDecorations(gotoHoverDecorations, [])
    gotoHoverEd.updateOptions({ mouseStyle: 'text' })
  }
  gotoHoverDecorations = []
  gotoHoverEd = null
}

function applyGotoHover(
  ed: import('monaco-editor').editor.IStandaloneCodeEditor,
  position: { lineNumber: number; column: number },
) {
  if (!monacoMod || review.value) {
    clearGotoHover()
    return
  }
  const model = ed.getModel()
  if (!model) {
    clearGotoHover()
    return
  }
  const ident = identifierAt(model, position)
  if (!ident) {
    clearGotoHover()
    return
  }
  const range = {
    startLineNumber: position.lineNumber,
    startColumn: ident.startColumn,
    endLineNumber: position.lineNumber,
    endColumn: ident.endColumn,
  }
  if (gotoHoverEd && gotoHoverEd !== ed) clearGotoHover()
  gotoHoverEd = ed
  gotoHoverDecorations = ed.deltaDecorations(gotoHoverDecorations, [
    {
      range,
      options: {
        inlineClassName: 'ca-goto-hover',
        stickiness: monacoMod.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
      },
    },
  ])
  ed.updateOptions({ mouseStyle: 'default' })
}

function onWindowBlur() {
  gotoModHeld = false
  lastGotoMouse = null
  clearGotoHover()
}

function onGotoModifierKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && chipOpen.value && !inlineOpen.value) {
    hideInlineChip()
  }
  if (e.altKey || e.shiftKey) {
    if (gotoModHeld) {
      gotoModHeld = false
      clearGotoHover()
    }
    return
  }
  const isModKey = e.key === 'Control' || e.key === 'Meta'
  if (e.type === 'keydown' && (isModKey || e.ctrlKey || e.metaKey)) {
    gotoModHeld = e.ctrlKey || e.metaKey
    if (gotoModHeld && lastGotoMouse) applyGotoHover(lastGotoMouse.ed, lastGotoMouse.position)
    return
  }
  if (e.type === 'keyup' && isModKey) {
    gotoModHeld = e.ctrlKey || e.metaKey
    if (!gotoModHeld) clearGotoHover()
  }
}

function overlayAt(
  ed: import('monaco-editor').editor.IStandaloneCodeEditor,
  pos: { lineNumber: number; column: number },
  opts?: { above?: boolean },
) {
  const vis = ed.getScrolledVisiblePosition(pos)
  const wrap = wrapEl.value
  const dom = ed.getDomNode()
  if (!vis || !wrap || !dom) return { left: 16, top: 48 }
  const edRect = dom.getBoundingClientRect()
  const wrapRect = wrap.getBoundingClientRect()
  let left = edRect.left - wrapRect.left + vis.left
  let top = edRect.top - wrapRect.top + vis.top + vis.height + 8
  if (opts?.above) {
    top = edRect.top - wrapRect.top + vis.top - 36
    if (top < 8) top = edRect.top - wrapRect.top + vis.top + vis.height + 6
  }
  const maxL = Math.max(8, wrap.clientWidth - 28)
  const maxT = Math.max(8, wrap.clientHeight - 28)
  left = Math.min(Math.max(8, left), maxL)
  if (!opts?.above && top > wrap.clientHeight - 160) {
    top = Math.max(8, edRect.top - wrapRect.top + vis.top - 12)
  }
  top = Math.min(Math.max(8, top), maxT)
  return { left, top }
}

function rangeAfterReplace(
  start: { startLineNumber: number; startColumn: number },
  text: string,
) {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const endLineNumber = start.startLineNumber + lines.length - 1
  const endColumn = lines.length === 1 ? start.startColumn + lines[0].length : lines[lines.length - 1].length + 1
  return {
    startLineNumber: start.startLineNumber,
    startColumn: start.startColumn,
    endLineNumber,
    endColumn,
  }
}

function markInlineRange(
  ed: import('monaco-editor').editor.IStandaloneCodeEditor,
  range: { startLineNumber: number; startColumn: number; endLineNumber: number; endColumn: number },
) {
  if (!monacoMod) return
  inlineDecorations = ed.deltaDecorations(inlineDecorations, [
    {
      range,
      options: {
        className: 'ca-inline-edit',
        stickiness: monacoMod.editor.TrackedRangeStickiness.AlwaysGrowsWhenTypingAtEdges,
      },
    },
  ])
}

function clearInlineDecorations(ed?: import('monaco-editor').editor.IStandaloneCodeEditor | null) {
  const target = ed || activeEditor()
  if (target && inlineDecorations.length) inlineDecorations = target.deltaDecorations(inlineDecorations, [])
  inlineDecorations = []
}

function closeInlineEdit(restore: boolean) {
  inlineGen += 1
  const ed = activeEditor()
  if (restore && inlinePreviewApplied && ed) {
    const model = ed.getModel()
    const range = inlineDecorations[0] && model ? model.getDecorationRange(inlineDecorations[0]) : null
    if (range) {
      ed.pushUndoStop()
      ed.executeEdits('inline-edit-reject', [{ range, text: inlineOriginal.value, forceMoveMarkers: true }])
      ed.pushUndoStop()
    }
  }
  clearInlineDecorations(ed)
  inlinePreviewApplied = false
  inlineOpen.value = false
  inlinePhase.value = 'prompt'
  inlineError.value = ''
  inlineReplacement.value = ''
}

function openInlineEdit() {
  if (review.value || editorReadOnly()) return
  const ed = activeEditor()
  const model = ed?.getModel()
  const path = store.activePath
  if (!ed || !model || !path) return
  gotoOpen.value = false
  hideInlineChip()
  if (inlineOpen.value && inlinePhase.value === 'prompt') {
    return
  }
  if (inlineOpen.value && inlinePhase.value === 'diff') closeInlineEdit(true)
  let sel = ed.getSelection()
  if (!sel || sel.isEmpty()) {
    const pos = ed.getPosition()
    if (!pos) return
    const expanded = expandInlineRange(model, pos)
    skipSelectionChip = true
    ed.setSelection({
      selectionStartLineNumber: expanded.startLineNumber,
      selectionStartColumn: expanded.startColumn,
      positionLineNumber: expanded.endLineNumber,
      positionColumn: expanded.endColumn,
    })
    sel = ed.getSelection()
    if (!sel) return
  }
  const original = model.getValueInRange(sel)
  if (!original.trim()) {
    toast.info(t('editor.inlineEditEmpty'))
    return
  }
  inlineOriginal.value = original
  inlineReplacement.value = original
  inlineInstruction.value = ''
  inlineError.value = ''
  inlinePhase.value = 'prompt'
  inlinePreviewApplied = false
  inlineLineLabel.value =
    sel.startLineNumber === sel.endLineNumber
      ? `L${sel.startLineNumber}`
      : `L${sel.startLineNumber}–${sel.endLineNumber}`
  const pos = overlayAt(ed, { lineNumber: sel.startLineNumber, column: sel.startColumn })
  inlineLeft.value = pos.left
  inlineTop.value = pos.top
  markInlineRange(ed, sel)
  inlineOpen.value = true
  ed.focus()
}

async function submitInlineEdit() {
  const ed = activeEditor()
  const model = ed?.getModel()
  const path = store.activePath
  const instruction = inlineInstruction.value.trim()
  if (!ed || !model || !path || !instruction) return
  if (!store.hasConfiguredModel) {
    toast.warning(t('chat.needModel'))
    window.dispatchEvent(new Event('ca-open-models'))
    return
  }
  const range = inlineDecorations[0] ? model.getDecorationRange(inlineDecorations[0]) : ed.getSelection()
  if (!range) return
  const selection = model.getValueInRange(range)
  inlineOriginal.value = selection
  const prefixStart = Math.max(1, range.startLineNumber - 40)
  const suffixEnd = Math.min(model.getLineCount(), range.endLineNumber + 40)
  const prefix = model.getValueInRange({
    startLineNumber: prefixStart,
    startColumn: 1,
    endLineNumber: range.startLineNumber,
    endColumn: range.startColumn,
  })
  const suffix = model.getValueInRange({
    startLineNumber: range.endLineNumber,
    startColumn: range.endColumn,
    endLineNumber: suffixEnd,
    endColumn: model.getLineMaxColumn(suffixEnd),
  })
  inlinePhase.value = 'loading'
  inlineError.value = ''
  const gen = ++inlineGen
  try {
    const data = await api<{ replacement: string; unchanged?: boolean }>(
      `/api/workspaces/${store.workspaceId}/inline-edit`,
      {
        method: 'POST',
        body: JSON.stringify({
          path,
          instruction,
          selection,
          prefix,
          suffix,
          language: langOf(path),
          model_id: store.modelId || undefined,
        }),
      },
    )
    const replacement = data.replacement ?? selection
    if (gen !== inlineGen || !inlineOpen.value) return
    if (data.unchanged || replacement === selection) {
      inlinePhase.value = 'prompt'
      toast.info(t('editor.inlineEditNoChange'))
      return
    }
    ed.pushUndoStop()
    ed.executeEdits('inline-edit', [{ range, text: replacement, forceMoveMarkers: true }])
    ed.pushUndoStop()
    inlinePreviewApplied = true
    inlineReplacement.value = replacement
    markInlineRange(ed, rangeAfterReplace(range, replacement))
    inlinePhase.value = 'diff'
  } catch (err) {
    if (gen !== inlineGen || !inlineOpen.value) return
    const raw = err instanceof Error ? err.message : String(err)
    if (raw.includes('llm.no_model')) {
      toast.warning(t('chat.needModel'))
      window.dispatchEvent(new Event('ca-open-models'))
    }
    inlineError.value = raw
    inlinePhase.value = 'prompt'
  }
}

function acceptInlineEdit() {
  inlinePreviewApplied = false
  closeInlineEdit(false)
  activeEditor()?.focus()
}

function rejectInlineEdit() {
  closeInlineEdit(true)
  activeEditor()?.focus()
}

async function jumpToHit(hit: GotoHit) {
  gotoOpen.value = false
  await store.openChatFilePath(hit.path, hit.line)
}

function showGotoPeek(
  ed: import('monaco-editor').editor.IStandaloneCodeEditor,
  pos: { lineNumber: number; column: number },
  symbol: string,
  hits: GotoHit[],
) {
  const place = overlayAt(ed, pos)
  gotoSymbolName.value = symbol
  gotoHits.value = hits
  gotoActive.value = 0
  gotoLeft.value = place.left
  gotoTop.value = place.top
  gotoOpen.value = true
}

async function gotoDefinition() {
  const ed = activeEditor()
  const pos = ed?.getPosition()
  if (!pos) return
  await gotoDefinitionAt(pos)
}

async function gotoDefinitionAt(position: { lineNumber: number; column: number }) {
  if (review.value) return
  const ed = activeEditor()
  const model = ed?.getModel()
  const path = store.activePath
  if (!ed || !model || !path) return
  if (inlineOpen.value) closeInlineEdit(inlinePreviewApplied)
  hideInlineChip()
  const ident = identifierAt(model, position)
  if (!ident) {
    toast.info(t('editor.gotoNoSymbol'))
    return
  }
  const local: GotoHit[] = findLocalDefinitions(model, ident.word)
    .filter((h) => h.line !== position.lineNumber)
    .map((h) => ({ path, line: h.line, text: h.text, kind: 'definition' }))
  let remote: GotoHit[] = []
  if (store.workspaceId) {
    try {
      const data = await api<{ hits: GotoHit[] }>(
        `/api/workspaces/${store.workspaceId}/goto?symbol=${encodeURIComponent(ident.word)}&from_path=${encodeURIComponent(path)}`,
      )
      remote = data.hits || []
    } catch {
      /* search may be unavailable */
    }
  }
  const seen = new Set(local.map((h) => `${h.path}:${h.line}`))
  const merged = [...local]
  for (const hit of remote) {
    const key = `${hit.path}:${hit.line}`
    if (hit.path === path && hit.line === position.lineNumber) continue
    if (seen.has(key)) continue
    seen.add(key)
    merged.push(hit)
  }
  if (!merged.length) {
    toast.info(t('editor.gotoNotFound', { symbol: ident.word }))
    return
  }
  if (merged.length === 1) {
    await jumpToHit(merged[0])
    return
  }
  showGotoPeek(ed, position, ident.word, merged)
}

watch(
  () => store.activePath,
  () => {
    if (inlineOpen.value) closeInlineEdit(inlinePreviewApplied)
    hideInlineChip()
    gotoOpen.value = false
  },
)

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
  bindEditorContextMenu(editor)
  bindEditorCommands(editor)
  editor.onDidFocusEditorText(() => {
    focusedPane.value = 'primary'
    if (primaryPath.value) store.activateFile(primaryPath.value)
  })
  host.value.addEventListener('copy', onEditorCopy)
  primaryPath.value = store.activePath
  showPath(store.activePath)
  window.addEventListener('ca-theme', onTheme as EventListener)
  window.addEventListener('ca-file-reload', onReload as EventListener)
  window.addEventListener('ca-focus-editor', onFocusEditor as EventListener)
  window.addEventListener('ca-editor-save', onEditorSaveEvent as EventListener)
  window.addEventListener('ca-inline-edit', onInlineEditEvent as EventListener)
  window.addEventListener('ca-goto-definition', onGotoEvent as EventListener)
  window.addEventListener('ca-run-file', onRunFileEvent as EventListener)
  window.addEventListener('keydown', onGotoModifierKey, true)
  window.addEventListener('keyup', onGotoModifierKey, true)
  window.addEventListener('blur', onWindowBlur)
  window.addEventListener('keydown', onReviewKey)
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
  if (e.key === 'ArrowUp' && canCycleChange.value) {
    e.preventDefault()
    cycleDiff(-1)
    return
  }
  if (e.key === 'ArrowDown' && canCycleChange.value) {
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
    showDiff(detail.path, current.before, current.after, { readOnly: true })
  } else if (store.gitEditorDiff[detail.path] && store.activePath === detail.path) {
    const gd = store.gitEditorDiff[detail.path]
    showDiff(detail.path, gd.original, detail.content, { readOnly: Boolean(gd.modifiedReadonly) })
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
      review.value?.before,
      review.value?.after,
      store.activeReviewIndexFor(store.activePath),
      htmlPreview.value,
      gitDiff.value?.original,
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
  () => review.value?.blockId,
  (id) => {
    if (id && splitMode.value !== 'none') closeSplit('primary')
  },
)
watch(gitDiff, (gd) => {
  if (gd && splitMode.value !== 'none') closeSplit('primary')
})

watch(
  () => store.openFiles.map((f) => f.path).join('\0'),
  () => {
    if (secondaryPath.value && !store.openFiles.some((f) => f.path === secondaryPath.value)) {
      secondaryPath.value = store.openFiles.find((f) => f.path !== primaryPath.value)?.path ?? null
      if (splitMode.value !== 'none') showPathOn(secondaryEditor, secondaryPath.value)
    }
    if (primaryPath.value && !store.openFiles.some((f) => f.path === primaryPath.value)) {
      primaryPath.value = store.activePath
    }
    const keep = new Set(store.openFiles.map((f) => f.path))
    for (const [path, model] of models) {
      if (!keep.has(path)) {
        if (editor?.getModel() === model) editor.setModel(null)
        if (secondaryEditor?.getModel() === model) secondaryEditor.setModel(null)
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
  window.removeEventListener('ca-editor-save', onEditorSaveEvent as EventListener)
  window.removeEventListener('ca-inline-edit', onInlineEditEvent as EventListener)
  window.removeEventListener('ca-goto-definition', onGotoEvent as EventListener)
  window.removeEventListener('ca-run-file', onRunFileEvent as EventListener)
  window.removeEventListener('keydown', onGotoModifierKey, true)
  window.removeEventListener('keyup', onGotoModifierKey, true)
  window.removeEventListener('blur', onWindowBlur)
  window.removeEventListener('keydown', onReviewKey)
  editorCtxDisposable?.dispose()
  editorCtxDisposable = null
  for (const d of editorInputDisposables) d.dispose()
  editorInputDisposables = []
  closeInlineEdit(true)
  hideInlineChip()
  clearGotoHover()
  gotoOpen.value = false
  disposeSecondaryEditor()
  for (const model of models.values()) model.dispose()
  for (const model of origModels.values()) model.dispose()
  models.clear()
  origModels.clear()
  diffEditor?.dispose()
  diffEditor = null
  hunkDiffDisposable?.dispose()
  hunkDiffDisposable = null
  hunkWidgets = []
  hunkZoneIdsMod = []
  hunkZoneIdsOrig = []
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
  editorMenu.value = null
  tabMenu.value = { x: e.clientX, y: e.clientY, path }
}

function toAbsolutePath(rel: string): string {
  const root = (store.workspace?.root_path || '').trim()
  if (!root) return rel
  if (!rel) return root
  const winStyle = /^[A-Za-z]:[\\/]/.test(root) || root.includes('\\')
  const sep = winStyle ? '\\' : '/'
  const normalizedRoot = root.replace(/[\\/]+$/, '')
  const normalizedRel = rel.replace(/^[\\/]+/, '').replace(/[\\/]+/g, sep)
  return `${normalizedRoot}${sep}${normalizedRel}`
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    /* ignore */
  }
}

function activeEditor() {
  if (review.value || gitDiff.value) return diffEditor?.getModifiedEditor() || null
  if (splitMode.value !== 'none' && focusedPane.value === 'secondary') return secondaryEditor
  return editor
}

function editorHasSelection() {
  const ed = activeEditor()
  if (!ed) return false
  const sel = ed.getSelection()
  return Boolean(sel && !sel.isEmpty())
}

function editorSelectionText() {
  const ed = activeEditor()
  if (!ed) return ''
  const model = ed.getModel()
  const sel = ed.getSelection()
  if (!model || !sel || sel.isEmpty()) return ''
  return model.getValueInRange(sel)
}

function editorReadOnly() {
  return Boolean(store.openFile?.readonly || review.value)
}

const tabMenuItems = computed((): ContextMenuItem[] => {
  const path = tabMenu.value?.path
  if (!path) return []
  const files = store.openFiles
  const index = files.findIndex((f) => f.path === path)
  const file = files[index]
  return [
    { id: 'save', label: t('editor.save'), icon: 'save', disabled: !file || file.readonly || !file.dirty },
    { id: 'reload', label: t('editor.reload'), icon: 'refresh', disabled: !file },
    { id: 'sep-file', separator: true },
    { id: 'add-to-chat', label: t('editor.addToChat'), icon: 'chat' },
    { id: 'reveal', label: t('editor.revealInExplorer'), icon: 'tree' },
    { id: 'open-terminal', label: t('editor.openInTerminal'), icon: 'terminal' },
    {
      id: 'run-file',
      label: t('editor.runFile'),
      icon: 'play',
      disabled: !isRunnableScript(path) || Boolean(file?.readonly),
    },
    { id: 'sep-split', separator: true },
    {
      id: 'split-right',
      label: t('editor.splitRight'),
      icon: 'panel-right',
      disabled: Boolean(showingDiff.value),
    },
    {
      id: 'split-down',
      label: t('editor.splitDown'),
      icon: 'panel-bottom',
      disabled: Boolean(showingDiff.value),
    },
    {
      id: 'close-split',
      label: t('editor.closeSplit'),
      icon: 'close',
      disabled: splitMode.value === 'none',
    },
    { id: 'sep-path', separator: true },
    { id: 'copy-relative', label: t('editor.copyRelativePath'), icon: 'path-relative' },
    { id: 'copy-absolute', label: t('editor.copyAbsolutePath'), icon: 'path-absolute' },
    { id: 'sep-close', separator: true },
    { id: 'close', label: t('editor.close'), icon: 'close' },
    { id: 'close-others', label: t('editor.closeOthers'), icon: 'close-others', disabled: files.length < 2 },
    { id: 'close-left', label: t('editor.closeLeft'), icon: 'close-left', disabled: index <= 0 },
    { id: 'close-right', label: t('editor.closeRight'), icon: 'close-right', disabled: index < 0 || index >= files.length - 1 },
    { id: 'close-all', label: t('editor.closeAll'), icon: 'close-all', disabled: files.length === 0 },
  ]
})

const tabMenuActions: Record<string, (path: string) => void | Promise<void>> = {
  save: async (path) => {
    store.activateFile(path)
    await onEditorSave()
  },
  reload: async (path) => {
    await store.reloadOpenFile(path)
  },
  'add-to-chat': (path) => {
    window.dispatchEvent(new CustomEvent('ca-add-chat-mention', {
      detail: { name: fileName(path), path, is_dir: false },
    }))
  },
  reveal: async (path) => {
    await store.revealInTree(path)
    window.dispatchEvent(new Event('ca-open-explorer'))
  },
  'open-terminal': (path) => {
    window.dispatchEvent(new CustomEvent('ca-open-terminal', { detail: { cwd: store.parentPath(path) } }))
  },
  'run-file': async (path) => {
    store.activateFile(path)
    await runActiveScript(path)
  },
  'split-right': async (path) => {
    await splitEditor('right', path)
  },
  'split-down': async (path) => {
    await splitEditor('down', path)
  },
  'close-split': () => closeSplit('primary'),
  'copy-relative': async (path) => copyText(path),
  'copy-absolute': async (path) => copyText(toAbsolutePath(path)),
  close: (path) => store.closeFile(path),
  'close-others': (path) => store.closeOtherFiles(path),
  'close-left': (path) => store.closeFilesToTheLeft(path),
  'close-right': (path) => store.closeFilesToTheRight(path),
  'close-all': () => store.closeAllFiles(),
}

async function onTabMenuSelect(id: string) {
  const path = tabMenu.value?.path
  if (!path) return
  await tabMenuActions[id]?.(path)
}

const editorMenuItems = computed((): ContextMenuItem[] => {
  if (!editorMenu.value || !store.activePath) return []
  const path = store.activePath
  const hasSel = editorHasSelection()
  const readOnly = editorReadOnly()
  const file = store.openFile
  const inReview = Boolean(review.value)
  const items: ContextMenuItem[] = []
  if (inReview && review.value) {
    items.push(
      { id: 'accept-hunk', label: t('editor.acceptHunk'), icon: 'check' },
      { id: 'reject-hunk', label: t('editor.rejectHunk'), icon: 'close', danger: true },
      { id: 'accept-block', label: t('editor.acceptBlock'), icon: 'check' },
      { id: 'reject-block', label: t('editor.rejectBlock'), icon: 'close', danger: true },
      { id: 'sep-review', separator: true },
    )
  }
  if (!inReview) {
    items.push(
      { id: 'cut', label: t('editor.cut'), icon: 'cut', disabled: readOnly || !hasSel },
      { id: 'copy', label: t('editor.copy'), icon: 'copy', disabled: !hasSel },
      { id: 'paste', label: t('editor.paste'), icon: 'paste', disabled: readOnly },
      { id: 'sep-edit', separator: true },
      {
        id: 'format',
        label: t('editor.formatDocument'),
        icon: 'sparkles',
        disabled: readOnly || !canFormatPath(path),
      },
      { id: 'inline-edit', label: t('editor.inlineEdit'), icon: 'file-edit', disabled: readOnly },
      { id: 'goto-definition', label: t('editor.gotoDefinition'), icon: 'search' },
      { id: 'sep-format', separator: true },
    )
  } else {
    items.push(
      { id: 'copy', label: t('editor.copy'), icon: 'copy', disabled: !hasSel },
      { id: 'sep-edit', separator: true },
    )
  }
  items.push(
    { id: 'add-selection', label: t('editor.addSelectionToChat'), icon: 'chat-plus', disabled: !hasSel },
    { id: 'add-to-chat', label: t('editor.addToChat'), icon: 'chat' },
    { id: 'sep-nav', separator: true },
    { id: 'reveal', label: t('editor.revealInExplorer'), icon: 'tree' },
    { id: 'open-terminal', label: t('editor.openInTerminal'), icon: 'terminal' },
    {
      id: 'run-file',
      label: t('editor.runFile'),
      icon: 'play',
      disabled: !canRunScript.value,
    },
    { id: 'copy-relative', label: t('editor.copyRelativePath'), icon: 'path-relative' },
    { id: 'copy-absolute', label: t('editor.copyAbsolutePath'), icon: 'path-absolute' },
    { id: 'sep-file', separator: true },
    { id: 'save', label: t('editor.save'), icon: 'save', disabled: !file || file.readonly || !file.dirty || inReview },
    { id: 'reload', label: t('editor.reload'), icon: 'refresh', disabled: inReview },
    { id: 'find', label: t('editor.find'), icon: 'search' },
  )
  return items
})

async function formatActiveDocument() {
  const path = store.activePath
  const file = store.openFile
  const ed = activeEditor()
  if (!path || !file || !ed || editorReadOnly() || review.value) return
  if (!canFormatPath(path)) return
  const model = ed.getModel()
  if (!model) return
  const content = model.getValue()
  const formatted = await formatDocumentText(path, content)
  if (formatted == null || formatted === content) return
  const full = model.getFullModelRange()
  ed.pushUndoStop()
  ed.executeEdits('format', [{ range: full, text: formatted, forceMoveMarkers: true }])
  ed.pushUndoStop()
  store.updateOpenContent(path, formatted)
}

async function onEditorMenuSelect(id: string) {
  const path = store.activePath
  if (!path) return
  const ed = activeEditor()
  if (id === 'accept-hunk') {
    const current = review.value
    const change = currentLineChange()
    if (current && change) {
      await store.acceptReviewHunk(current.path, change, current.blockId)
    }
    return
  }
  if (id === 'reject-hunk') {
    const current = review.value
    const change = currentLineChange()
    if (current && change) {
      await store.rejectReviewHunk(current.path, change, current.blockId)
    }
    return
  }
  if (id === 'accept-block') {
    const current = review.value
    if (current) await store.acceptReview(current.path, current.blockId)
    return
  }
  if (id === 'reject-block') {
    const current = review.value
    if (current) await store.rejectReview(current.path, current.blockId)
    return
  }
  if (id === 'cut') {
    const text = editorSelectionText()
    if (!text || editorReadOnly() || !ed) return
    await copyText(text)
    const sel = ed.getSelection()
    if (sel) ed.executeEdits('cut', [{ range: sel, text: '', forceMoveMarkers: true }])
    return
  }
  if (id === 'copy') {
    const text = editorSelectionText()
    if (text) await copyText(text)
    return
  }
  if (id === 'paste') {
    if (!ed || editorReadOnly()) return
    ed.focus()
    try {
      const text = await navigator.clipboard.readText()
      const sel = ed.getSelection()
      if (text && sel) ed.executeEdits('paste', [{ range: sel, text, forceMoveMarkers: true }])
    } catch {
      ed.trigger('keyboard', 'editor.action.clipboardPasteAction', null)
    }
    return
  }
  if (id === 'format') {
    await formatActiveDocument()
    return
  }
  if (id === 'inline-edit') {
    openInlineEdit()
    return
  }
  if (id === 'goto-definition') {
    void gotoDefinition()
    return
  }
  if (id === 'add-selection') {
    const text = editorSelectionText()
    if (!text || !ed) return
    const sel = ed.getSelection()
    if (!sel) return
    window.dispatchEvent(new CustomEvent('ca-add-chat-mention', {
      detail: {
        name: fileName(path),
        path,
        is_dir: false,
        lineStart: sel.startLineNumber,
        lineEnd: sel.endLineNumber,
      },
    }))
    return
  }
  if (id === 'add-to-chat') {
    window.dispatchEvent(new CustomEvent('ca-add-chat-mention', {
      detail: { name: fileName(path), path, is_dir: false },
    }))
    return
  }
  if (id === 'reveal') {
    await store.revealInTree(path)
    window.dispatchEvent(new Event('ca-open-explorer'))
    return
  }
  if (id === 'open-terminal') {
    const dir = store.parentPath(path)
    window.dispatchEvent(new CustomEvent('ca-open-terminal', { detail: { cwd: dir } }))
    return
  }
  if (id === 'run-file') {
    await runActiveScript(path)
    return
  }
  if (id === 'copy-relative') {
    await copyText(path)
    return
  }
  if (id === 'copy-absolute') {
    await copyText(toAbsolutePath(path))
    return
  }
  if (id === 'save') {
    await onEditorSave()
    return
  }
  if (id === 'reload') {
    await store.reloadOpenFile(path)
    return
  }
  if (id === 'find') {
    ed?.focus()
    ed?.trigger('menu', 'actions.find', null)
  }
}

function bindEditorContextMenu(ed: import('monaco-editor').editor.IStandaloneCodeEditor) {
  editorCtxDisposable?.dispose()
  editorCtxDisposable = ed.onContextMenu((e) => {
    const ev = e.event
    ev.preventDefault()
    ev.stopPropagation()
    hideInlineChip()
    tabMenu.value = null
    editorMenu.value = { x: ev.posx, y: ev.posy }
  })
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
          :class="{
            active: store.activePath === file.path,
            dragging: dragTabPath === file.path,
            'drop-before': dropTabPath === file.path && dragTabPath && dragTabPath !== file.path,
            'in-other-pane':
              splitMode !== 'none' &&
              file.path !== store.activePath &&
              (file.path === primaryPath || file.path === secondaryPath),
          }"
          :title="file.path"
          :aria-selected="store.activePath === file.path"
          :draggable="true"
          tabindex="0"
          @click="activateTab(file.path)"
          @dblclick.prevent="onTabDblClick(file.path)"
          @keydown.enter.prevent="activateTab(file.path)"
          @auxclick="onTabAux(file.path, $event)"
          @contextmenu="onTabContext(file.path, $event)"
          @dragstart="onTabDragStart(file.path, $event)"
          @dragover="onTabDragOver(file.path, $event)"
          @dragleave="onTabDragLeave(file.path)"
          @drop="onTabDrop(file.path, $event)"
          @dragend="onTabDragEnd"
        >
          <FileTreeIcon kind="file" :path="file.path" :size="16" />
          <span class="name">{{ fileName(file.path) }}{{ file.dirty ? ' •' : '' }}</span>
          <span v-if="store.pendingReviewCount(file.path)" class="mark">diff</span>
          <button type="button" class="ghost-icon-btn ftab-close" title="关闭" @click.stop="store.closeFile(file.path)">
            <AppIcon name="close" :size="12" :stroke-width="1.75" />
          </button>
        </div>
      </div>
      <div class="file-bar-tools">
        <button
          v-if="canRunScript"
          type="button"
          class="ghost-icon-btn file-bar-run"
          :title="t('editor.runFileHint')"
          :disabled="runningScript"
          :aria-label="t('editor.runFile')"
          @click="runActiveScript()"
        >
          <AppIcon name="play" :size="15" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ghost-icon-btn"
          :title="t('editor.splitRight')"
          :disabled="showingDiff || store.openFiles.length === 0"
          @click="splitEditor('right')"
        >
          <AppIcon name="panel-right" :size="15" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ghost-icon-btn"
          :title="t('editor.splitDown')"
          :disabled="showingDiff || store.openFiles.length === 0"
          @click="splitEditor('down')"
        >
          <AppIcon name="panel-bottom" :size="15" :stroke-width="1.75" />
        </button>
        <button
          v-if="splitMode !== 'none'"
          type="button"
          class="ghost-icon-btn"
          :title="t('editor.closeSplit')"
          @click="closeSplit('primary')"
        >
          <AppIcon name="close" :size="15" :stroke-width="1.75" />
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
    </header>
    <div v-if="store.fileNotice" class="file-notice" role="status">
      <span>{{ store.fileNotice }}</span>
      <button type="button" class="ghost-icon-btn notice-x" @click="store.clearFileNotice()">
        <AppIcon name="close" :size="14" :stroke-width="1.75" />
      </button>
    </div>
    <div class="review-bar">
      <span class="review-path" :title="store.activePath || ''">
        {{ store.activePath || t('editor.openFromSidebar') }}
      </span>
      <div v-if="gitDiff && !review" class="git-diff-bar">
        <span>{{ t('git.diffVsHead') }}</span>
        <button
          type="button"
          class="ghost-icon-btn"
          :title="t('git.closeEditorDiff')"
          @click="store.clearGitEditorDiff(store.activePath)"
        >
          <AppIcon name="close" :size="14" :stroke-width="1.75" />
        </button>
      </div>
      <div v-if="pendingCount" class="review-bar-controls">
        <div class="review-nav" role="navigation" :aria-label="t('editor.reviewNav')">
        <div class="review-nav-group">
          <span class="group-label">{{ t('editor.diffLabel') }}</span>
          <button
            type="button"
            class="nav-btn"
            :disabled="!canCycleChange"
            :title="canCycleDiff ? t('editor.prevDiff') : t('editor.prevFile')"
            @click="cycleDiff(-1)"
          >
            <AppIcon name="chevron-up" :size="14" :stroke-width="1.75" />
          </button>
          <span class="nav-label">{{ t('editor.diffNav', { i: fileReviewIndex, n: Math.max(fileReviewCount, 1) }) }}</span>
          <button
            type="button"
            class="nav-btn"
            :disabled="!canCycleChange"
            :title="canCycleDiff ? t('editor.nextDiff') : t('editor.nextFile')"
            @click="cycleDiff(1)"
          >
            <AppIcon name="chevron-down" :size="14" :stroke-width="1.75" />
          </button>
        </div>
        <span class="review-nav-sep" aria-hidden="true" />
        <div class="review-nav-group">
          <span class="group-label">{{ t('editor.fileLabel') }}</span>
          <button
            type="button"
            class="nav-btn"
            :disabled="!canCycleFile"
            :title="t('editor.prevFile')"
            @click="cycleFile(-1)"
          >
            <AppIcon name="chevron-left" :size="14" :stroke-width="1.75" />
          </button>
          <span class="nav-label">{{ t('editor.fileNav', { i: filePathIndex || 1, n: filePendingPathCount }) }}</span>
          <button
            type="button"
            class="nav-btn"
            :disabled="!canCycleFile"
            :title="t('editor.nextFile')"
            @click="cycleFile(1)"
          >
            <AppIcon name="chevron-right" :size="14" :stroke-width="1.75" />
          </button>
        </div>
      </div>
      </div>
    </div>
    <div
      ref="wrapEl"
      class="host-wrap"
      :class="{
        'split-right': splitMode === 'right',
        'split-down': splitMode === 'down',
      }"
    >
      <div
        class="editor-pane"
        :class="{ focused: splitMode !== 'none' && focusedPane === 'primary' }"
        @mousedown="focusPane('primary')"
      >
        <FilePreviewHost
          v-if="primaryShowFilePreview && primaryFile && !showingDiff"
          :file="primaryFile"
          class="host"
        />
        <MarkdownPreview
          v-else-if="primaryShowMarkdownPreview && primaryFile"
          :content="primaryFile.content"
          :path="primaryFile.path"
          class="host"
        />
        <div
          ref="host"
          class="host"
          :class="{
            hidden: showingDiff || primaryShowMarkdownPreview || primaryShowFilePreview,
          }"
        />
        <div ref="diffHost" class="host" :class="{ hidden: !showingDiff || splitMode !== 'none' }" />
        <div v-if="!panePath('primary') && !showingDiff" class="empty">
          <AppIcon name="file" :size="28" />
          <p>{{ t('editor.openFromSidebar') }}</p>
        </div>
      </div>
      <div
        v-if="splitMode !== 'none'"
        class="editor-pane secondary"
        :class="{ focused: focusedPane === 'secondary' }"
        @mousedown="focusPane('secondary')"
      >
        <div ref="secondaryHost" class="host" />
        <div v-if="!secondaryPath" class="empty">
          <AppIcon name="file" :size="28" />
          <p>{{ t('editor.splitEmpty') }}</p>
        </div>
      </div>
      <InlineEditChip
        v-if="chipOpen && !inlineOpen"
        :left="chipLeft"
        :top="chipTop"
        @open="openInlineEdit"
      />
      <InlineEditWidget
        v-if="inlineOpen"
        :instruction="inlineInstruction"
        :phase="inlinePhase"
        :original="inlineOriginal"
        :replacement="inlineReplacement"
        :error="inlineError"
        :left="inlineLeft"
        :top="inlineTop"
        :line-label="inlineLineLabel"
        @update:instruction="inlineInstruction = $event"
        @submit="submitInlineEdit"
        @accept="acceptInlineEdit"
        @reject="rejectInlineEdit"
        @close="closeInlineEdit(inlinePreviewApplied)"
      />
      <GotoPeek
        v-if="gotoOpen"
        :hits="gotoHits"
        :active="gotoActive"
        :left="gotoLeft"
        :top="gotoTop"
        :symbol="gotoSymbolName"
        @update:active="gotoActive = $event"
        @pick="jumpToHit"
        @close="gotoOpen = false"
      />
    </div>
    <ContextMenu
      v-if="tabMenu"
      :x="tabMenu.x"
      :y="tabMenu.y"
      :items="tabMenuItems"
      @select="onTabMenuSelect"
      @close="tabMenu = null"
    />
    <ContextMenu
      v-if="editorMenu"
      :x="editorMenu.x"
      :y="editorMenu.y"
      :items="editorMenuItems"
      @select="onEditorMenuSelect"
      @close="editorMenu = null"
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
.ftab.dragging {
  opacity: 0.45;
}
.ftab.drop-before {
  box-shadow: inset 2px 0 0 var(--primary);
}
.ftab.in-other-pane {
  color: var(--text-h);
  opacity: 0.85;
}
.file-bar-tools {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.file-bar-run {
  color: var(--primary);
}
.file-bar-run:hover:not(:disabled) {
  background: var(--primary-soft);
  opacity: 1;
}
.file-bar-tools .ghost-icon-btn:disabled {
  opacity: 0.28;
  cursor: default;
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
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 2px 8px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--bg);
  color: var(--text);
  font-size: 11px;
  overflow: hidden;
  position: relative;
  z-index: 80;
}
.review-path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-secondary);
  user-select: none;
}
.git-diff-bar {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
}
.review-bar-controls {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
  overflow: visible;
}
.review-nav {
  display: inline-flex;
  align-items: center;
  flex-shrink: 1;
  min-width: 0;
}
.review-nav-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 0 1px;
}
.group-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
  user-select: none;
}
.review-nav-sep {
  width: 1px;
  height: 16px;
  margin: 0 4px;
  background: var(--border);
  flex-shrink: 0;
}
.review-bar .nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 22px;
  width: auto;
  min-width: 22px;
  padding: 0 2px;
  border: 0;
  border-radius: calc(var(--radius-md) - 2px);
  background: transparent;
  color: var(--text-h);
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  flex-shrink: 0;
  transition: opacity 0.15s ease, background-color 0.12s ease, color 0.12s ease;
}
.review-bar .nav-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text-h) 8%, transparent);
  opacity: 1;
}
.review-bar .nav-btn:disabled {
  opacity: 0.28;
  cursor: default;
}
.review-bar .nav-label {
  min-width: 0;
  padding: 0 2px;
  font-size: 10px;
  font-weight: 600;
  font-family: var(--mono);
  color: var(--text-secondary);
  text-align: center;
  white-space: nowrap;
  user-select: none;
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
  display: flex;
}
.host-wrap.split-right {
  flex-direction: row;
}
.host-wrap.split-down {
  flex-direction: column;
}
.editor-pane {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  outline: none;
}
.editor-pane.secondary {
  border-left: var(--border-width) solid var(--border);
}
.host-wrap.split-down .editor-pane.secondary {
  border-left: 0;
  border-top: var(--border-width) solid var(--border);
}
.editor-pane.focused {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 35%, transparent);
}
.host {
  height: 100%;
  flex: 1;
  min-height: 0;
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
  pointer-events: none;
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
.ca-inline-edit {
  background: color-mix(in srgb, var(--primary) 14%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 35%, transparent);
}
.ca-goto-hover {
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
  cursor: pointer !important;
}
.ca-hunk-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  height: 30px;
  padding: 3px;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: color-mix(in srgb, var(--panel-bg) 92%, transparent);
  backdrop-filter: blur(10px);
  box-shadow: var(--dropdown-shadow);
  line-height: 1;
  white-space: nowrap;
  pointer-events: auto;
  z-index: 40;
}
html[data-theme='dark'] .ca-hunk-actions {
  box-shadow: var(--dropdown-shadow-dark);
}
.ca-hunk-nav,
.ca-hunk-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 24px;
  min-height: 24px;
  box-sizing: border-box;
  line-height: 1;
  border-radius: 999px;
}
.ca-hunk-nav {
  gap: 0;
  padding: 0 4px 0 2px;
}
.ca-hunk-index {
  min-width: 2.2em;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 650;
  font-family: var(--mono);
  color: var(--text-h);
  user-select: none;
  white-space: nowrap;
  text-align: center;
  letter-spacing: 0.02em;
}
.ca-hunk-btn {
  padding: 0 10px;
  border: 0;
  background: transparent;
  color: var(--text-h);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
  pointer-events: auto;
  z-index: 41;
}
.ca-hunk-btn.is-nav {
  width: 20px;
  min-width: 20px;
  padding: 0;
  color: var(--text-secondary);
}
.ca-hunk-btn:disabled {
  display: none;
}
.ca-hunk-btn.is-reject {
  color: var(--danger);
}
.ca-hunk-btn.is-accept {
  color: var(--primary);
}
.ca-hunk-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text-h) 7%, transparent);
}
.ca-hunk-btn.is-nav:hover:not(:disabled) {
  color: var(--text-h);
}
.ca-hunk-btn.is-reject:hover {
  background: color-mix(in srgb, var(--danger) 12%, transparent);
}
.ca-hunk-btn.is-accept:hover {
  background: color-mix(in srgb, var(--primary) 14%, transparent);
}
</style>
