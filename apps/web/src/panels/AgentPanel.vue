<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, toRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { TrAttachments, TrSender, UploadButton, VoiceButton } from '@opentiny/tiny-robot'
import type { Attachment } from '@opentiny/tiny-robot'
import { useAppStore } from '@/stores/app'
import { rendererFor } from '@/renderers'
import type { Block } from '@/protocol/applyEvent'
import ChatInputToolbar from '@/components/ChatInputToolbar.vue'
import AppIcon from '@/components/AppIcon.vue'
import ConversationSwitcher from '@/components/ConversationSwitcher.vue'
import UserMessageHistoryMenu from '@/components/UserMessageHistoryMenu.vue'
import AssistantMessageBody from '@/components/AssistantMessageBody.vue'
import ChatContextUsageButton from '@/components/ChatContextUsageButton.vue'
import ChatContextUsageDialog from '@/components/ChatContextUsageDialog.vue'
import { scrollToBottom, scrollToTop } from '@/utils/smoothScroll'
import { useVirtualList } from '@/composables/useVirtualList'
import { useChatAttachments } from '@/composables/useChatAttachments'
import { openImageLightbox } from '@/composables/useImageLightbox'
import { useContextUsagePreview } from '@/composables/useContextUsagePreview'
import { paletteShortcutLabel } from '@/utils/relativeTime'
import {
  attachmentFileMatchers,
  detectAttachmentFileTypeFromMeta,
  UPLOAD_ACCEPT,
  UPLOAD_MAX_COUNT,
  UPLOAD_MAX_SIZE_MB,
} from '@/utils/fileTypes'
import type { LlmModel } from '@/types/llm'
import type { PendingFilePayload } from '@/types/contextUsage'
import type { Editor } from '@tiptap/core'
import { fileMentionExtension, type FileMentionAttrs } from '@/editor/fileMentionExtension'
import { skillMentionExtension } from '@/editor/skillMentionExtension'
import {
  fileNameFromPath,
  hasInlineMentions,
  mentionToken,
  messageHasInlineMentions,
  messageTextToEditorDoc,
  normalizeClipboardText,
  parseMentionSegments,
  serializeParagraphs,
  segmentsToInlineNodes,
  type FileMentionItem,
  type PasteSegment,
} from '@/utils/fileMention'

const senderExtensions = [fileMentionExtension, skillMentionExtension]

const { t } = useI18n()
const store = useAppStore()
const commandShortcut = paletteShortcutLabel()
const scroller = ref<HTMLElement | null>(null)
const virtualList = useVirtualList(toRef(store, 'messages'), scroller, { threshold: 40 })
const messageRows = computed(() =>
  virtualList.enabled.value
    ? virtualList.visibleItems.value
    : store.messages.map((item, index) => ({ item, index })),
)

/* ---- message actions ---- */
const copyToast = ref(false)
let copyToastTimer: ReturnType<typeof setTimeout> | null = null

const expandedMsgs = ref(new Set<string>())
const MSG_COLLAPSE_LEN = 300

function isLongMsg(msg: (typeof store.messages)[0]): boolean {
  const text = msg.blocks.map((b) => b.text || '').join('')
  return text.length > MSG_COLLAPSE_LEN || text.split('\n').length > 8
}

function toggleExpand(id: string) {
  const s = new Set(expandedMsgs.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expandedMsgs.value = s
}

function isAssistantStreaming(msg: (typeof store.messages)[0]): boolean {
  if (msg.role !== 'assistant') return false
  if (msg.ended_at) return false
  if (!running()) return false
  return store.messages.at(-1)?.id === msg.id
}

function onWorkToggle() {
  // Expanding work must not yank the viewport to the bottom.
  pauseFollow()
}

function msgPlainText(msg: (typeof store.messages)[0]): string {
  return msg.blocks
    .filter((b) => b.type === 'user.text' || b.type === 'assistant.markdown')
    .map((b) => b.text)
    .join('\n')
    .trim()
}


async function copyMsg(msg: (typeof store.messages)[0]) {
  await navigator.clipboard.writeText(msgPlainText(msg)).catch(() => {})
  if (copyToastTimer) clearTimeout(copyToastTimer)
  copyToast.value = true
  copyToastTimer = setTimeout(() => { copyToast.value = false }, 2000)
}

function focusSenderEnd() {
  const editor = getTipTapEditor()
  if (editor) {
    editor.chain().focus('end').run()
    return
  }
  const el = document.querySelector('.agent-sender .ProseMirror') as HTMLElement | null
  el?.focus()
}

function msgAttachmentFiles(msg: (typeof store.messages)[0]): PendingFilePayload[] {
  const files: PendingFilePayload[] = []
  for (const block of msg.blocks) {
    if (block.type !== 'user.text') continue
    const meta = block.meta as { files?: PendingFilePayload[] }
    if (!Array.isArray(meta.files)) continue
    for (const file of meta.files) {
      if (file?.url) files.push(file)
    }
  }
  return files
}

function msgSkillName(msg: (typeof store.messages)[0]): string | null {
  for (const block of msg.blocks) {
    if (block.type !== 'user.text') continue
    const skill = (block.meta as { skill?: { name?: string } } | undefined)?.skill
    if (skill?.name) return skill.name
  }
  return null
}

function startEdit(msg: (typeof store.messages)[0]) {
  setSenderDraftFromMessage(msgPlainText(msg))
  restoreAttachments(msgAttachmentFiles(msg))
  const skill = msgSkillName(msg)
  store.setConversationSkill(skill)
  nextTick(() => {
    const editor = getTipTapEditor()
    if (editor && skill) {
      removeAllSkillMentions(editor)
      editor.chain().focus('start').insertSkillMention({ name: skill }).insertContent(' ').run()
      draft.value = editor.getText()
    }
    syncMentionFilesFromEditor()
    focusSenderEnd()
  })
}

function fmtDuration(msg: (typeof store.messages)[0]): string {
  if (!msg.created_at || !msg.ended_at) return ''
  const ms = new Date(msg.ended_at).getTime() - new Date(msg.created_at).getTime()
  if (ms < 0) return ''
  const sec = ms / 1000
  if (sec < 60) return `${sec.toFixed(1)}s`
  const min = Math.floor(sec / 60)
  const s = (sec % 60).toFixed(0)
  return `${min}m ${s}s`
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function userMessagePreview(msg: (typeof store.messages)[0]) {
  const text = msgPlainText(msg).replace(/\s+/g, ' ').trim()
  if (text) return text.length > 56 ? `${text.slice(0, 56)}…` : text
  const files = msgAttachmentFiles(msg)
  if (files.some((f) => detectAttachmentFileTypeFromMeta(f.name || '', f.type || '') === 'image')) {
    return t('chat.historyImage')
  }
  if (files.length) return t('chat.historyAttachment')
  return t('chat.historyEmpty')
}

type UserHistoryEntry = { id: string; preview: string; time: string }

const userHistoryEntries = computed<UserHistoryEntry[]>(() =>
  store.messages
    .filter((m) => m.role === 'user')
    .map((m) => ({
      id: m.id,
      preview: userMessagePreview(m),
      time: fmtTime(m.created_at),
    })),
)

const activeHistoryId = ref<string | null>(null)
let historyObs: IntersectionObserver | null = null

function scrollToMessage(msgId: string) {
  pauseFollow()
  activeHistoryId.value = msgId
  const idx = store.messages.findIndex((m) => m.id === msgId)
  if (idx >= 0 && virtualList.enabled.value) {
    nextTick(() => {
      virtualList.scrollToIndex(idx, 'smooth')
    })
    return
  }
  nextTick(() => {
    const container = scroller.value
    const el = document.getElementById(`msg-${msgId}`)
    if (!container || !el) return
    locking = true
    const top = el.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 12
    scrollToTop(container, top, 'smooth')
    requestAnimationFrame(() => {
      locking = false
    })
  })
}

function userMessageById(id: string) {
  return store.messages.find((m) => m.id === id && m.role === 'user') ?? null
}

function editHistoryMessage(id: string) {
  const msg = userMessageById(id)
  if (!msg) return
  startEdit(msg)
}

function copyHistoryMessage(id: string) {
  const msg = userMessageById(id)
  if (!msg) return
  void copyMsg(msg)
}

function setupHistoryObserver() {
  historyObs?.disconnect()
  historyObs = null
  const root = scroller.value
  if (!root || !userHistoryEntries.value.length) return
  historyObs = new IntersectionObserver(
    (entries) => {
      const hit = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      const id = hit?.target instanceof HTMLElement ? hit.target.id.replace(/^msg-/, '') : ''
      if (id) activeHistoryId.value = id
    },
    { root, threshold: [0.15, 0.4, 0.7], rootMargin: '-12% 0px -58% 0px' },
  )
  root.querySelectorAll('article.msg-wrap.user').forEach((node) => historyObs!.observe(node))
}
const timelineInner = ref<HTMLElement | null>(null)
const sender = ref<{
  clear: () => void
  setContent: (content: string) => void
  focus?: () => void
  editor?: SenderEditor | { value?: SenderEditor }
} | null>(null)
const draft = ref('')

const quickPrompts = computed(() => [
  { label: t('chat.promptExplainLabel'), text: t('chat.promptExplainText') },
  { label: t('chat.promptReviewLabel'), text: t('chat.promptReviewText') },
  { label: t('chat.promptTestLabel'), text: t('chat.promptTestText') },
  { label: t('chat.promptLintLabel'), text: t('chat.promptLintText') },
])

function useQuickPrompt(text: string) {
  setSenderDraft(text)
  nextTick(() => {
    const el = document.querySelector('.agent-sender .ProseMirror') as HTMLElement | null
    el?.focus()
  })
}

/* ---- @ file mention ---- */
type MentionItem = FileMentionItem
type SkillMentionItem = {
  name: string
  description: string
  source: string
  invalid_reason?: string | null
}

const mentionOpen = ref(false)
const mentionTab = ref<'files' | 'skills'>('files')
const mentionQuery = ref('')
const mentionDir = ref('')
const mentionActiveIdx = ref(0)
const mentionFiles = ref<MentionItem[]>([])

function resolvePinnedMentionItem(): MentionItem | null {
  const path = store.activePath
  if (!path) return null
  const parent = store.parentPath(path)
  const inParent = store.childrenOf(parent).find((i) => i.path === path)
  if (inParent) return inParent
  const name = path.split('/').filter(Boolean).pop() || path
  const isFile = store.openFiles.some((f) => f.path === path)
  return { name, path, is_dir: !isFile }
}

const mentionItems = computed(() => {
  const dir = mentionDir.value
  const q = mentionQuery.value.toLowerCase()
  let items = store.childrenOf(dir)
  if (q) items = items.filter((i) => i.name.toLowerCase().includes(q))
  if (!dir) {
    const pinned = resolvePinnedMentionItem()
    if (pinned && (!q || pinned.name.toLowerCase().includes(q))) {
      items = [pinned, ...items.filter((i) => i.path !== pinned.path)]
    }
  }
  return items
})

const mentionSkillItems = computed<SkillMentionItem[]>(() => {
  const q = mentionQuery.value.toLowerCase()
  return (store.skills as SkillMentionItem[])
    .filter((s) => !s.invalid_reason)
    .filter((s) => {
      if (!q) return true
      return `${s.name} ${s.description} ${s.source}`.toLowerCase().includes(q)
    })
})

const activeSkillName = computed(() => store.conversationSkillName())

watch(mentionOpen, (open) => {
  if (open && !store.skills.length) void store.loadSkills()
})

watch(mentionDir, async (d) => {
  if (!store.childrenMap[d]) await store.loadTree(d)
})

function getTipTapEditor(): Editor | null {
  const raw = sender.value?.editor
  if (!raw) return null
  if (typeof (raw as Editor).chain === 'function') return raw as Editor
  const inner = (raw as { value?: Editor }).value
  return inner && typeof inner.chain === 'function' ? inner : null
}

function getAtTriggerFromEditor(editor: Editor): { from: number; to: number; query: string } | null {
  const { $from } = editor.state.selection
  if (!$from.parent.isTextblock || !editor.state.selection.empty) return null
  const textBefore = $from.parent.textBetween(0, $from.parentOffset, undefined, '\ufffc')
  const lastAt = textBefore.lastIndexOf('@')
  if (lastAt < 0) return null
  const after = textBefore.slice(lastAt + 1)
  if (/\s/.test(after)) return null
  return {
    from: $from.start() + lastAt,
    to: $from.pos,
    query: after,
  }
}

function refreshMentionTrigger() {
  const editor = getTipTapEditor()
  if (!editor) {
    mentionOpen.value = false
    return
  }
  const trigger = getAtTriggerFromEditor(editor)
  if (trigger) {
    mentionQuery.value = trigger.query
    if (!mentionOpen.value) {
      mentionDir.value = ''
      mentionActiveIdx.value = 0
      mentionTab.value = 'files'
      const pinned = resolvePinnedMentionItem()
      if (pinned) void store.loadTree(store.parentPath(pinned.path) || '')
    }
    mentionOpen.value = true
  } else {
    mentionOpen.value = false
  }
}

let mentionEditorOff: (() => void) | null = null

function bindMentionEditorEvents() {
  mentionEditorOff?.()
  mentionEditorOff = null
  const editor = getTipTapEditor()
  if (!editor) return
  const handler = () => refreshMentionTrigger()
  editor.on('update', handler)
  editor.on('selectionUpdate', handler)
  mentionEditorOff = () => {
    editor.off('update', handler)
    editor.off('selectionUpdate', handler)
  }
}

function mentionItemFromAttrs(attrs: Record<string, unknown>): MentionItem {
  return {
    path: String(attrs.path || ''),
    name: String(attrs.name || ''),
    is_dir: Boolean(attrs.isDir),
    lineStart: attrs.lineStart != null ? Number(attrs.lineStart) : undefined,
    lineEnd: attrs.lineEnd != null ? Number(attrs.lineEnd) : undefined,
  }
}

function fileMentionAttrs(item: MentionItem): FileMentionAttrs {
  return {
    path: item.path,
    name: item.name,
    isDir: item.is_dir,
    lineStart: item.lineStart ?? null,
    lineEnd: item.lineEnd ?? null,
  }
}

function switchMentionTab(tab: 'files' | 'skills') {
  mentionTab.value = tab
  mentionActiveIdx.value = 0
  if (tab === 'skills' && !store.skills.length) void store.loadSkills()
}

function removeAllSkillMentions(editor: Editor) {
  const ranges: { from: number; to: number }[] = []
  editor.state.doc.descendants((node, pos) => {
    if (node.type.name === 'skillMention') {
      ranges.push({ from: pos, to: pos + node.nodeSize })
    }
  })
  if (!ranges.length) return
  let chain = editor.chain().focus()
  for (const range of ranges.reverse()) {
    chain = chain.deleteRange(range)
  }
  chain.run()
}

function editorSkillName(): string | null {
  const editor = getTipTapEditor()
  if (!editor) return store.conversationSkillName()
  let name: string | null = null
  editor.state.doc.descendants((node) => {
    if (node.type.name === 'skillMention') {
      name = String(node.attrs.name || '')
    }
  })
  return name
}

function syncSkillFromEditor() {
  store.setConversationSkill(editorSkillName())
}

function insertInlineSkillMention(skill: SkillMentionItem, replaceTrigger = false) {
  const editor = getTipTapEditor()
  if (!editor) {
    store.setConversationSkill(skill.name)
    return
  }
  removeAllSkillMentions(editor)
  let chain = editor.chain().focus()
  if (replaceTrigger) {
    const trigger = getAtTriggerFromEditor(editor)
    if (trigger) chain = chain.deleteRange({ from: trigger.from, to: trigger.to })
  }
  chain.insertSkillMention({ name: skill.name }).insertContent(' ').run()
  draft.value = editor.getText()
  store.setConversationSkill(skill.name)
}

function mentionSelectSkill(skill: SkillMentionItem) {
  mentionOpen.value = false
  nextTick(() => {
    insertInlineSkillMention(skill, true)
    refreshMentionTrigger()
    focusSenderEnd()
  })
}

function insertInlineMention(item: MentionItem, replaceTrigger = false) {
  const editor = getTipTapEditor()
  if (!editor) return
  const attrs = fileMentionAttrs(item)
  const chain = editor.chain().focus()
  if (replaceTrigger) {
    const trigger = getAtTriggerFromEditor(editor)
    if (trigger) chain.deleteRange({ from: trigger.from, to: trigger.to })
  }
  chain.insertFileMention(attrs).insertContent(' ').run()
  draft.value = editor.getText()
  syncMentionFilesFromEditor()
}

function mentionEnterDir(item: MentionItem) {
  if (!item.is_dir) return
  mentionDir.value = item.path
  mentionQuery.value = ''
  mentionActiveIdx.value = 0
  store.loadTree(item.path)
}

function mentionSelect(item: MentionItem, fromAt = true) {
  mentionOpen.value = false
  nextTick(() => {
    insertInlineMention(item, fromAt)
    refreshMentionTrigger()
    const el = document.querySelector('.agent-sender .ProseMirror') as HTMLElement | null
    el?.focus()
  })
}

function syncMentionFilesFromEditor() {
  const editor = getTipTapEditor()
  if (!editor) return
  const items: MentionItem[] = []
  editor.state.doc.descendants((node) => {
    if (node.type.name !== 'fileMention') return
    items.push(mentionItemFromAttrs(node.attrs as Record<string, unknown>))
  })
  mentionFiles.value = items.filter((item) => item.path)
}

function serializeMessageFromEditor(): { value: string; mentions: MentionItem[] } {
  const editor = getTipTapEditor()
  if (!editor) {
    return { value: plainTextFromDraft(draft.value), mentions: mentionFiles.value }
  }

  const mentions: MentionItem[] = []
  const partsByParagraph: Array<Array<{ kind: 'text'; value: string } | { kind: 'mention'; value: string }>> = []

  editor.state.doc.forEach((block) => {
    if (block.type.name !== 'paragraph') return
    const parts: Array<{ kind: 'text'; value: string } | { kind: 'mention'; value: string }> = []
    block.forEach((child) => {
      if (child.type.name === 'text') {
        parts.push({ kind: 'text', value: child.text || '' })
      } else if (child.type.name === 'fileMention') {
        const item = mentionItemFromAttrs(child.attrs as Record<string, unknown>)
        mentions.push(item)
        parts.push({ kind: 'mention', value: mentionToken(item) })
      }
    })
    partsByParagraph.push(parts)
  })

  return { value: normalizeSubmitText(serializeParagraphs(partsByParagraph)), mentions }
}

function insertPasteSegments(segments: PasteSegment[]) {
  const editor = getTipTapEditor()
  if (!editor) return
  const inline = segmentsToInlineNodes(segments)
  if (!inline.length) return
  editor.chain().focus().insertContent(inline).run()
  draft.value = editor.getText()
  syncMentionFilesFromEditor()
}

function onAddChatMention(e: Event) {
  const item = (e as CustomEvent<MentionItem>).detail
  if (!item?.path) return
  mentionSelect(item, false)
  window.dispatchEvent(new Event('ca-focus-agent'))
}

function mentionKeydown(e: KeyboardEvent) {
  if (!mentionOpen.value) return
  const items = mentionTab.value === 'files' ? mentionItems.value : mentionSkillItems.value
  const active = items[mentionActiveIdx.value]
  if (e.key === 'ArrowDown') { e.preventDefault(); mentionActiveIdx.value = (mentionActiveIdx.value + 1) % Math.max(1, items.length) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); mentionActiveIdx.value = (mentionActiveIdx.value - 1 + Math.max(1, items.length)) % Math.max(1, items.length) }
  else if (e.key === 'ArrowRight' && mentionTab.value === 'files' && active && 'is_dir' in active && active.is_dir) { e.preventDefault(); mentionEnterDir(active as MentionItem) }
  else if (e.key === 'Enter' && items.length) {
    e.preventDefault()
    e.stopPropagation()
    if (mentionTab.value === 'files') mentionSelect(active as MentionItem)
    else mentionSelectSkill(active as SkillMentionItem)
  }
  else if (e.key === 'Escape') { e.preventDefault(); mentionOpen.value = false }
  else if (e.key === 'Tab') {
    e.preventDefault()
    switchMentionTab(mentionTab.value === 'files' ? 'skills' : 'files')
  }
}

/* ---- sender resize ---- */
const SENDER_MIN_HEIGHT = 40
const SENDER_MAX_HEIGHT = 440
const senderContentHeight = ref<number | null>(null)

const senderStyle = computed(() => ({
  '--sender-min-height': `${SENDER_MIN_HEIGHT}px`,
  '--sender-max-height': `${SENDER_MAX_HEIGHT}px`,
  ...(senderContentHeight.value ? { '--sender-content-height': `${senderContentHeight.value}px` } : {}),
}))

type SenderEditor = {
  chain: () => {
    insertContentAt: (pos: number, content: string) => { focus: (pos?: string) => { run: () => boolean } }
  }
  commands: {
    setContent: (content: string, options?: { emitUpdate?: boolean }) => boolean
  }
  getText: () => string
  state: { doc: { content: { size: number } } }
}

function getSenderEditor(): SenderEditor | null {
  const raw = sender.value?.editor
  if (!raw) return null
  if (typeof (raw as SenderEditor).chain === 'function') return raw as SenderEditor
  const inner = (raw as { value?: SenderEditor }).value
  return inner && typeof inner.chain === 'function' ? inner : null
}

function escapeSenderHtml(text: string) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function plainTextToSenderHtml(text: string) {
  const normalized = text.replace(/\r\n/g, '\n')
  if (!normalized) return ''
  return normalized
    .split('\n')
    .map((line) => (line ? `<p>${escapeSenderHtml(line)}</p>` : '<p><br></p>'))
    .join('')
}

function setSenderDraft(text: string) {
  const normalized = text.replace(/\r\n/g, '\n')
  const editor = getSenderEditor()
  if (editor) {
    editor.commands.setContent(plainTextToSenderHtml(normalized), { emitUpdate: false })
    draft.value = editor.getText()
    return
  }
  draft.value = normalized
  sender.value?.setContent?.(normalized)
}

function resolveMentionIsDir(path: string) {
  if (store.childrenMap[path]) return true
  const parent = store.parentPath(path)
  const item = store.childrenOf(parent).find((i) => i.path === path)
  return item?.is_dir ?? false
}

function setSenderDraftFromMessage(text: string) {
  const normalized = text.replace(/\r\n/g, '\n')
  const editor = getTipTapEditor()
  if (editor && messageHasInlineMentions(normalized)) {
    editor.commands.setContent(messageTextToEditorDoc(normalized, resolveMentionIsDir), { emitUpdate: false })
    draft.value = editor.getText()
    syncMentionFilesFromEditor()
    return
  }
  setSenderDraft(normalized)
}

function readEditorLineHeight(pm: HTMLElement, last: HTMLElement) {
  const style = getComputedStyle(last.tagName === 'P' ? last : pm)
  if (style.lineHeight.endsWith('px')) return parseFloat(style.lineHeight)
  const font = parseFloat(style.fontSize) || 14
  const numeric = parseFloat(style.lineHeight)
  if (!Number.isNaN(numeric) && style.lineHeight !== 'normal') return numeric * font
  return last.getBoundingClientRect().height || 26
}

function insertBlankEditorLines(count: number) {
  const editor = getSenderEditor()
  if (editor) {
    editor.chain().insertContentAt(editor.state.doc.content.size, '<p><br></p>'.repeat(count)).focus('end').run()
    return
  }
  setSenderDraft(`${draft.value}${'\n'.repeat(count)}`)
  nextTick(() => sender.value?.focus?.())
}

function onSenderBlankPointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  const wrap = e.currentTarget as HTMLElement
  const content = wrap.querySelector('.tr-sender-content') as HTMLElement | null
  if (!content?.contains(e.target as Node)) return
  if ((e.target as HTMLElement).closest('button, a, input, textarea')) return

  const pm = wrap.querySelector('.ProseMirror') as HTMLElement | null
  if (!pm) return
  const last = (pm.lastElementChild as HTMLElement) || pm
  const lastBottom = last.getBoundingClientRect().bottom
  if (e.clientY <= lastBottom + 1) return

  const lineHeight = readEditorLineHeight(pm, last)
  const extra = Math.max(1, Math.round((e.clientY - lastBottom) / lineHeight))
  e.preventDefault()
  e.stopPropagation()
  insertBlankEditorLines(extra)
}

function onResizeHandlePointerDown(e: PointerEvent) {
  e.preventDefault()
  const startY = e.clientY
  const content = document.querySelector('.agent-sender .tr-sender-content') as HTMLElement | null
  const startH = content?.offsetHeight ?? 60
  const onMove = (ev: PointerEvent) => {
    const delta = startY - ev.clientY
    senderContentHeight.value = Math.max(SENDER_MIN_HEIGHT, Math.min(SENDER_MAX_HEIGHT, startH + delta))
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

const stick = ref(true)
const showScrollToBottom = computed(() => !stick.value && store.messages.length > 0)
const contextUsageOpen = ref(false)
const uploadError = ref('')
let locking = false
let followGen = 0
let pinRaf = 0
let resizeObs: ResizeObserver | null = null

const {
  attachments,
  addFiles,
  removeAttachment,
  retryUpload,
  clearAttachments,
  restoreAttachments,
  getPendingFiles,
  hasUploadingAttachments,
} = useChatAttachments()

const pendingFiles = computed(() => getPendingFiles())

function attachmentPreviewItems() {
  return attachments.value
    .filter((item) => item.status === 'success' && item.url && item.fileType === 'image')
    .map((item) => ({
      src: String(item.url),
      alt: item.name || '',
      title: item.name || '',
    }))
}

function onAttachmentPreview(event: MouseEvent, file: Attachment) {
  event.preventDefault()
  const items = attachmentPreviewItems()
  const index = items.findIndex((item) => item.src === file.url)
  openImageLightbox(items, index >= 0 ? index : 0)
}

const selectedModel = computed(() => {
  for (const provider of store.providers) {
    const model = (provider.models || []).find((m: LlmModel) => m.id === store.modelId)
    if (model) return model
  }
  return null
})

const modelSupportsVision = computed(() => {
  const model = selectedModel.value
  if (!model) return false
  if (model.supports_vision) return true
  if (model.capabilities?.vision?.supported) return true
  const id = (model.model_id || '').toLowerCase()
  return id.includes('vision') || id.includes('deepseek-vl')
})

const visionAttachHint = computed(() => {
  if (!pendingFiles.value.length) return ''
  if (modelSupportsVision.value) return ''
  return t('chat.visionWarn')
})

const { preview: contextUsagePreview, loading: contextUsagePreviewLoading } = useContextUsagePreview({
  conversationId: toRef(store, 'conversationId'),
  userContent: draft,
  thinkingLevel: toRef(store, 'thinkingLevel'),
  mode: toRef(store, 'mode'),
  files: pendingFiles,
})

const contextUsageRingPercent = computed(() => contextUsagePreview.value?.recommendedUsagePercent ?? 0)
const contextUsageRingLevel = computed(() => contextUsagePreview.value?.level ?? 'normal')
const inputBlocked = computed(() => hasUploadingAttachments())

const queuedMessages = computed(() => store.conversationQueue())
const queueExpanded = ref(true)

function toggleQueueExpanded() {
  queueExpanded.value = !queueExpanded.value
}

function onSendQueuedNow(id: string) {
  stick.value = true
  void store.sendQueuedNow(id)
}

const speechConfig = computed(() => ({
  lang: 'zh-CN',
  continuous: true,
  interimResults: true,
}))

function running() {
  return store.isRunBusy()
}

function distanceToBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight
}

function pauseFollow() {
  stick.value = false
  followGen += 1
  if (pinRaf) {
    cancelAnimationFrame(pinRaf)
    pinRaf = 0
  }
}

function jumpToEnd(behavior: ScrollBehavior = 'smooth') {
  if (!stick.value) return
  const el = scroller.value
  if (!el) return
  const token = followGen
  const top = Math.max(0, el.scrollHeight - el.clientHeight)
  if (behavior === 'auto' && Math.abs(el.scrollTop - top) < 2) return
  locking = true
  scrollToTop(el, top, behavior)
  requestAnimationFrame(() => {
    if (token !== followGen || !stick.value) {
      locking = false
      return
    }
    scrollToBottom(el, behavior)
    requestAnimationFrame(() => {
      locking = false
    })
  })
}

function scrollToEnd() {
  if (!stick.value) return
  jumpToEnd('smooth')
}

function resumeStickScroll() {
  void pinToBottom()
}

function onScroll() {
  virtualList.onScroll()
  if (locking) return
  const el = scroller.value
  if (!el) return
  if (distanceToBottom(el) > 16) pauseFollow()
  else stick.value = true
}

function onWheel(e: WheelEvent) {
  if (e.deltaY < 0) pauseFollow()
}

function onPointerDown(e: PointerEvent) {
  const el = scroller.value
  if (!el) return
  if (e.offsetX >= el.clientWidth - 18) pauseFollow()
}

function scheduleStickScroll() {
  if (!stick.value) return
  if (pinRaf) return
  pinRaf = requestAnimationFrame(() => {
    pinRaf = 0
    if (!stick.value) return
    jumpToEnd('auto')
  })
}

/** Force pin to bottom (conversation switch / initial load). */
async function pinToBottom() {
  stick.value = true
  followGen += 1
  const token = followGen

  const attempt = () => {
    if (token !== followGen || !stick.value) return
    jumpToEnd('smooth')
  }

  await nextTick()
  attempt()
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  attempt()

  // Async message blocks / images continue growing after first paint.
  for (let i = 0; i < 10; i++) {
    await new Promise<void>((resolve) => window.setTimeout(resolve, 60))
    if (token !== followGen) return
    attempt()
  }
}

onMounted(() => {
  if (timelineInner.value) {
    resizeObs = new ResizeObserver(() => {
      scheduleStickScroll()
    })
    resizeObs.observe(timelineInner.value)
  }
  if (store.messages.length) void pinToBottom()
  window.addEventListener('ca-add-chat-mention', onAddChatMention)
  nextTick(() => {
    bindMentionEditorEvents()
    setupHistoryObserver()
  })
})

onBeforeUnmount(() => {
  mentionEditorOff?.()
  mentionEditorOff = null
  resizeObs?.disconnect()
  resizeObs = null
  historyObs?.disconnect()
  historyObs = null
  if (pinRaf) cancelAnimationFrame(pinRaf)
  window.removeEventListener('ca-add-chat-mention', onAddChatMention)
})

watch(
  () => sender.value?.editor,
  () => nextTick(() => bindMentionEditorEvents()),
)

watch(
  () => store.conversationId,
  () => {
    stick.value = true
  },
)

watch(
  () => [store.conversationId, store.messages.length] as const,
  async ([, len], prev) => {
    if (!len) {
      activeHistoryId.value = null
      return
    }
    const switched = !prev || prev[0] !== store.conversationId
    const filled = switched || (prev[1] === 0 && len > 0)
    if (switched || filled) await pinToBottom()
    nextTick(() => setupHistoryObserver())
  },
)

watch(
  () => store.runStatus,
  () => {
    if (running() && stick.value) scheduleStickScroll()
  },
)

function clearSender() {
  draft.value = ''
  sender.value?.clear?.()
  sender.value?.setContent?.('')
}

function normalizeSubmitText(text: string) {
  return text
    .replace(/\r\n/g, '\n')
    .replace(/\n\n/g, '\n')
    .replace(/[^\S\n]+/g, ' ')
    .replace(/ *\n */g, '\n')
    .trim()
}

function plainTextFromDraft(text: string) {
  return normalizeSubmitText(text.replace(/\r\n/g, '\n'))
}

function buildPayload(_text: string) {
  syncSkillFromEditor()
  const { value, mentions } = serializeMessageFromEditor()
  if (hasUploadingAttachments()) return null
  const files = getPendingFiles()
  const skillName = store.conversationSkillName()
  if (!value && !files.length && !mentions.length && !skillName) return null
  return { value, refs: [] as { type: 'file'; path: string }[], files }
}

function afterSubmitClear() {
  mentionFiles.value = []
  store.setConversationSkill(null)
  clearSender()
  clearAttachments()
  uploadError.value = ''
  nextTick(() => {
    clearSender()
    scrollToEnd()
  })
}

function onSubmit(text: string) {
  const payload = buildPayload(text)
  if (!payload) return
  stick.value = true
  void store.send(payload.value, payload.refs, payload.files)
  afterSubmitClear()
}

function onSubmitNow() {
  const payload = buildPayload(draft.value)
  if (!payload) return
  stick.value = true
  void store.sendNow(payload.value, payload.refs, payload.files)
  afterSubmitClear()
}

function onSenderCaptureKeydown(e: KeyboardEvent) {
  if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return
  if (!running()) return
  syncMentionFilesFromEditor()
  const value = plainTextFromDraft(draft.value || '')
  const files = getPendingFiles()
  const mentions = mentionFiles.value
  if ((!value && !files.length && !mentions.length && !editorSkillName()) || hasUploadingAttachments()) return
  e.preventDefault()
  e.stopPropagation()
  if (e.altKey) onSubmitNow()
  else onSubmit(draft.value)
}

function onCancel() {
  if (running()) store.stop()
}

function handleFileSelect(files: File[]) {
  uploadError.value = ''
  addFiles(files)
}

function onComposerPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (items?.length) {
    const imageFiles: File[] = []
    for (const item of items) {
      if (item.kind !== 'file' || !item.type.startsWith('image/')) continue
      const file = item.getAsFile()
      if (file) imageFiles.push(file)
    }
    if (imageFiles.length) {
      e.preventDefault()
      handleFileSelect(imageFiles)
      return
    }
  }

  const text = e.clipboardData?.getData('text/plain')
  if (!text) return

  const clip = normalizeClipboardText(text)
  const copyCtx = store.editorCopyContext
  if (copyCtx && clip === normalizeClipboardText(copyCtx.text)) {
    e.preventDefault()
    insertInlineMention({
      path: copyCtx.path,
      name: fileNameFromPath(copyCtx.path),
      is_dir: false,
      lineStart: copyCtx.startLine,
      lineEnd: copyCtx.endLine,
    })
    return
  }

  if (hasInlineMentions(clip)) {
    e.preventDefault()
    insertPasteSegments(parseMentionSegments(clip, resolveMentionIsDir))
  }
}

function handleUploadError(error: Error) {
  uploadError.value = error.message
}

function handleSpeechError(error: Error) {
  uploadError.value = error.message || t('chat.sttFailed')
}

function openContextUsageDialog() {
  contextUsageOpen.value = true
}
</script>

<template>
  <div class="panel-shell agent">
    <ConversationSwitcher>
      <template #actions>
        <UserMessageHistoryMenu
          :entries="userHistoryEntries"
          :active-id="activeHistoryId"
          @select="scrollToMessage"
          @edit="editHistoryMessage"
          @copy="copyHistoryMessage"
        />
      </template>
    </ConversationSwitcher>
    <Teleport to="body">
      <Transition name="toast-fade">
        <div v-if="copyToast" class="copy-toast">
          <AppIcon name="check" :size="16" />
          {{ t('chat.copied') }}
        </div>
      </Transition>
    </Teleport>
    <div class="agent-main">
      <div ref="scroller" class="timeline" @scroll="onScroll" @wheel="onWheel" @pointerdown="onPointerDown">
        <div ref="timelineInner" class="timeline-inner">
        <div v-if="!store.messages.length" class="empty">
          <div class="empty-icon" aria-hidden="true">
            <AppIcon name="atom" :size="32" />
          </div>
          <p class="empty-lead">{{ t('chat.emptyLead') }}</p>
          <p class="empty-hint"><kbd>{{ commandShortcut }}</kbd> {{ t('chat.emptyHint') }}</p>
          <div class="quick-prompts">
            <button
              v-for="item in quickPrompts"
              :key="item.label"
              type="button"
              class="quick-prompt"
              @click="useQuickPrompt(item.text)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
        <div v-if="virtualList.enabled.value" class="virtual-spacer" :style="{ height: `${virtualList.paddingTop.value}px` }" />
        <article
          v-for="row in messageRows"
          :key="row.item.id"
          :id="'msg-' + row.item.id"
          :ref="virtualList.enabled.value ? (el) => virtualList.setItemEl(row.item.id, el as Element | null) : undefined"
          :class="['msg-wrap', row.item.role]"
        >
          <template v-if="row.item.role === 'user'">
            <div class="msg-bubble" :class="{ collapsed: !expandedMsgs.has(row.item.id) && isLongMsg(row.item) }">
              <section v-for="block in row.item.blocks" :key="block.id" class="block">
                <component :is="rendererFor(block.type)" :block="block as Block" />
              </section>
            </div>
            <button
              v-if="isLongMsg(row.item)"
              type="button"
              class="msg-expand-btn"
              @click="toggleExpand(row.item.id)"
            >{{ expandedMsgs.has(row.item.id) ? t('chat.collapse') : t('chat.expandAll') }}</button>
          </template>
          <template v-else>
            <AssistantMessageBody
              :msg="row.item"
              :streaming="isAssistantStreaming(row.item)"
              @toggle="onWorkToggle"
            />
          </template>
          <div v-if="row.item.role === 'user' || !isAssistantStreaming(row.item)" class="msg-bar" :class="row.item.role">
            <span class="msg-time">
              <template v-if="row.item.created_at">{{ fmtTime(row.item.created_at) }}</template>
              <template v-if="row.item.role === 'assistant' && row.item.ended_at"> · {{ fmtTime(row.item.ended_at) }} · {{ t('time.duration', { value: fmtDuration(row.item) }) }}</template>
            </span>
            <div class="msg-actions">
              <button v-if="row.item.role === 'user'" type="button" class="msg-icon-btn" :title="t('common.edit')" @click="startEdit(row.item)">
                <AppIcon name="pencil" :size="14" />
              </button>
              <button type="button" class="msg-icon-btn" :title="t('common.copy')" @click="copyMsg(row.item)">
                <AppIcon name="copy" :size="14" />
              </button>
            </div>
          </div>
        </article>
        <div v-if="virtualList.enabled.value" class="virtual-spacer" :style="{ height: `${virtualList.paddingBottom.value}px` }" />
        <div v-if="running()" class="typing" aria-hidden="true">
          <span class="dots"><i /><i /><i /></span>
          <button type="button" class="stop-inline" @click="store.stop()">{{ t('common.stop') }}</button>
        </div>
        </div>
      </div>
    </div>
    <footer class="agent-footer">
      <!-- @ file picker popup -->
      <Transition name="mention-fade">
        <div v-if="mentionOpen" class="mention-popup">
          <div class="mention-tabs" role="tablist" :aria-label="t('chat.mentionTabs')">
            <button
              type="button"
              role="tab"
              class="mention-tab"
              :class="{ active: mentionTab === 'files' }"
              :aria-selected="mentionTab === 'files'"
              @mousedown.prevent="switchMentionTab('files')"
            >
              {{ t('chat.mentionTabFiles') }}
            </button>
            <button
              type="button"
              role="tab"
              class="mention-tab"
              :class="{ active: mentionTab === 'skills' }"
              :aria-selected="mentionTab === 'skills'"
              @mousedown.prevent="switchMentionTab('skills')"
            >
              {{ t('chat.mentionTabSkills') }}
            </button>
          </div>

          <template v-if="mentionTab === 'files'">
            <div v-if="mentionDir" class="mention-dir-back">
              <button type="button" class="mention-back-btn" @click="mentionDir = ''; mentionQuery = ''">
                <AppIcon name="arrow-left" :size="12" />
                {{ t('common.back') }}
              </button>
              <span class="mention-dir-label">{{ mentionDir }}</span>
            </div>
            <ul v-if="mentionItems.length" class="mention-list">
              <li
                v-for="(item, i) in mentionItems"
                :key="item.path"
                class="mention-item"
                :class="{ active: i === mentionActiveIdx, pinned: i === 0 && !mentionDir && resolvePinnedMentionItem()?.path === item.path }"
                @mouseenter="mentionActiveIdx = i"
                @mousedown.prevent="mentionSelect(item)"
              >
                <AppIcon :name="item.is_dir ? 'folder' : 'file'" :size="14" />
                <span class="mention-name">{{ item.name }}</span>
                <button
                  v-if="item.is_dir"
                  type="button"
                  class="mention-arrow"
                  :title="t('workspace.browse')"
                  @mousedown.prevent.stop="mentionEnterDir(item)"
                >
                  ›
                </button>
              </li>
            </ul>
            <p v-else class="mention-empty">{{ t('chat.mentionFilesEmpty') }}</p>
          </template>

          <template v-else>
            <ul v-if="mentionSkillItems.length" class="mention-list">
              <li
                v-for="(skill, i) in mentionSkillItems"
                :key="`${skill.source}:${skill.name}`"
                class="mention-item mention-skill-item"
                :class="{ active: i === mentionActiveIdx, selected: activeSkillName === skill.name }"
                @mouseenter="mentionActiveIdx = i"
                @mousedown.prevent="mentionSelectSkill(skill)"
              >
                <AppIcon name="book" :size="14" />
                <span class="mention-skill-copy">
                  <span class="mention-name">{{ skill.name }}</span>
                  <span class="mention-skill-desc">{{ skill.description || t('chat.mentionSkillNoDesc') }}</span>
                </span>
              </li>
            </ul>
            <p v-else class="mention-empty">{{ t('chat.mentionSkillsEmpty') }}</p>
          </template>
        </div>
      </Transition>
      <!-- @ mention chips -->
      <div v-if="queuedMessages.length" class="send-queue" :class="{ collapsed: !queueExpanded }">
        <div class="send-queue-head">
          <button type="button" class="queue-toggle" :aria-expanded="queueExpanded" @click="toggleQueueExpanded">
            <span class="queue-chevron" :class="{ open: queueExpanded }">›</span>
            <span>{{ t('chat.queued', { n: queuedMessages.length }) }}</span>
          </button>
          <button type="button" class="queue-clear" @click="store.clearConversationQueue()">{{ t('chat.clearQueue') }}</button>
        </div>
        <div v-show="queueExpanded" class="send-queue-body">
          <div v-for="(item, index) in queuedMessages" :key="item.id" class="send-queue-item">
            <span class="queue-index">{{ index + 1 }}</span>
            <span class="queue-text" :title="item.text">{{ item.text }}</span>
            <div class="queue-actions">
              <button type="button" class="queue-send" :title="t('chat.sendNow')" @click="onSendQueuedNow(item.id)">{{ t('common.send') }}</button>
              <button type="button" class="queue-remove" :title="t('common.remove')" @click="store.removeQueuedSend(item.id)">
                <AppIcon name="close" :size="12" />
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="agent-sender-stack">
        <Transition name="scroll-jump-fade">
          <button
            v-if="showScrollToBottom"
            type="button"
            class="scroll-to-bottom-btn"
            :title="t('chat.scrollToBottom')"
            :aria-label="t('chat.scrollToBottom')"
            @click="resumeStickScroll"
          >
            <AppIcon name="chevron" :size="18" />
          </button>
        </Transition>
      <div class="sender-resize-handle" @pointerdown="onResizeHandlePointerDown" :title="t('chat.resize')"></div>
      <div
        class="agent-sender-wrap"
        @pointerdown.capture="onSenderBlankPointerDown"
        @keydown.capture="onSenderCaptureKeydown"
        @keydown="mentionKeydown"
        @paste.capture="onComposerPaste"
      >
        <TrSender
          ref="sender"
          v-model="draft"
          class="agent-sender"
          :style="senderStyle"
          :extensions="senderExtensions"
          mode="multiple"
          submit-type="enter"
          :placeholder="running() ? t('chat.promptBusy') : t('chat.prompt')"
          :loading="running()"
          clearable
          @submit="onSubmit"
          @cancel="onCancel"
        >
          <template v-if="attachments.length" #header>
            <TrAttachments
              v-model:items="attachments"
              class="agent-attachments"
              wrap
              :file-matchers="attachmentFileMatchers"
              @remove="removeAttachment"
              @retry="retryUpload"
              @preview="onAttachmentPreview"
            />
          </template>

          <template #footer>
            <ChatInputToolbar />
          </template>

          <template #footer-right>
            <div class="agent-sender-actions">
              <ChatContextUsageButton
                :percent="contextUsageRingPercent"
                :level="contextUsageRingLevel"
                :loading="contextUsagePreviewLoading"
                :disabled="!store.conversationId"
                @click="openContextUsageDialog"
              />
              <UploadButton
                :tooltip="t('chat.uploadImage')"
                tooltip-placement="top"
                multiple
                :max-size="UPLOAD_MAX_SIZE_MB"
                :max-count="UPLOAD_MAX_COUNT"
                :accept="UPLOAD_ACCEPT"
                :disabled="inputBlocked"
                @select="handleFileSelect"
                @error="handleUploadError"
              />
              <VoiceButton
                :tooltip="t('chat.voiceInput')"
                tooltip-placement="top"
                :speech-config="speechConfig"
                :disabled="inputBlocked"
                @speech-error="handleSpeechError"
              />
            </div>
          </template>
        </TrSender>
      </div>
      </div>
      <p v-if="uploadError" class="agent-upload-error">{{ uploadError }}</p>
      <p v-else-if="visionAttachHint" class="agent-upload-hint">{{ visionAttachHint }}</p>
    </footer>

    <ChatContextUsageDialog
      :open="contextUsageOpen"
      :conversation-id="store.conversationId"
      :user-content="draft"
      :thinking-level="store.thinkingLevel"
      :thinking="store.thinking"
      :mode="store.mode"
      :files="pendingFiles"
      @close="contextUsageOpen = false"
    />
  </div>
</template>

<style scoped>
.agent { background: var(--page-bg); position: relative; }
.agent-main {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
}
.timeline {
  flex: 1;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overflow-anchor: none;
  scroll-behavior: smooth;
  scrollbar-gutter: auto;
  padding: 12px 20px 8px;
}
.timeline::-webkit-scrollbar-button {
  display: none;
  height: 0;
  width: 0;
}
.timeline-inner {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  width: 100%;
  min-height: min-content;
}
.virtual-spacer {
  flex: none;
  width: 100%;
}
.empty {
  align-self: center;
  width: min(100%, 420px);
  padding: 40px 12px 24px;
  text-align: center;
}
.empty-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  background: var(--primary-soft);
  color: var(--primary);
}
.empty-lead {
  margin: 0 0 8px;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
}
.empty-hint {
  margin: 0 0 16px;
  font-size: 12px;
  color: var(--text-muted);
}
.empty-hint kbd {
  font-family: var(--mono);
  font-size: 11px;
  padding: 1px 6px;
  margin-right: 4px;
  border-radius: 4px;
  border: var(--border-width) solid var(--border);
  background: var(--code-bg);
  color: var(--text-secondary);
}
.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
.quick-prompt {
  padding: 6px 12px;
  border: var(--border-width) solid var(--border);
  border-radius: 999px;
  background: var(--panel-bg);
  color: var(--text);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.quick-prompt:hover {
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
  color: var(--primary);
  background: var(--primary-soft);
}
article.msg-wrap.user {
  align-self: flex-end;
  margin-left: auto;
  margin-right: 0;
  width: fit-content;
  max-width: min(78%, 560px);
  margin-top: 12px;
  margin-bottom: 4px;
  overflow-anchor: none;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.msg-bubble {
  background: var(--code-bg);
  color: var(--text-h);
  padding: 8px 12px;
  border-radius: 10px 10px 4px 10px;
  width: fit-content;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
}
.msg-bubble :deep(.block) {
  width: fit-content;
  max-width: 100%;
}
.msg-wrap.user .msg-bubble {
  margin-left: auto;
  text-align: left;
}
.msg-bubble :deep(.markdown-body p) {
  margin: 0;
}
.msg-bubble.collapsed {
  max-height: 120px;
  overflow: hidden;
  position: relative;
}
.msg-bubble.collapsed::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 36px;
  background: linear-gradient(transparent, var(--code-bg));
  pointer-events: none;
}
.msg-expand-btn {
  display: block;
  margin-top: 2px;
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: var(--primary);
  font-size: 12px;
  cursor: pointer;
  align-self: flex-end;
}
.msg-expand-btn:hover { text-decoration: underline; }
article.msg-wrap.assistant {
  align-self: stretch;
  width: 100%;
  margin: 16px 0 8px;
  overflow-anchor: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.block + .block { margin-top: 2px; }

/* message action bar */
.msg-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
  opacity: 0;
  transition: opacity 0.15s ease;
}
article.msg-wrap:hover .msg-bar,
article.msg-wrap:focus-within .msg-bar {
  opacity: 1;
}
.msg-bar.user {
  flex-direction: row-reverse;
  align-self: flex-end;
}
.msg-time {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}
.msg-actions {
  display: flex;
  gap: 2px;
}
.msg-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.msg-icon-btn:hover { background: var(--bg-muted); color: var(--text-h); }
.msg-act-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11.5px;
  padding: 2px 7px;
  border: var(--border-width) solid var(--border);
  border-radius: 5px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}
.msg-act-btn:hover { background: var(--bg-muted); color: var(--text-h); }
.msg-act-primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.msg-act-primary:hover { opacity: 0.85; }

/* edit textarea */
.msg-edit-wrap.msg-bubble {
  padding: 8px 10px;
}
.msg-edit-textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 0;
  font-size: 13px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--text-h);
  resize: vertical;
  outline: none;
  font-family: inherit;
  line-height: 1.5;
}
.msg-edit-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  justify-content: flex-end;
}
.typing {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 28px;
  padding: 4px 2px 8px;
  color: var(--text-muted);
}
.stop-inline {
  border: 0;
  background: transparent;
  color: var(--primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}
.stop-inline:hover {
  background: var(--primary-soft);
}
.dots {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  animation: typing 1.05s ease-in-out infinite;
}
.dots i:nth-child(2) { animation-delay: 0.15s; }
.dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes typing {
  0%, 80%, 100% { opacity: 0.25; }
  40% { opacity: 1; }
}
footer.agent-footer {
  position: relative;
  border-top: 0;
  padding: 0 16px 16px;
  background: linear-gradient(to top, var(--page-bg) 72%, transparent);
}

.agent-sender-stack {
  position: relative;
  width: 100%;
}

.scroll-to-bottom-btn {
  position: absolute;
  left: 50%;
  bottom: calc(100% + 8px);
  z-index: 6;
  transform: translateX(-50%);
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  box-shadow: 0 4px 18px rgba(15, 23, 42, 0.12);
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}

html[data-theme='dark'] .scroll-to-bottom-btn {
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.35);
}

.scroll-to-bottom-btn:hover {
  color: var(--primary);
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
  transform: translateX(-50%) translateY(-1px);
}

.scroll-jump-fade-enter-active,
.scroll-jump-fade-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.scroll-jump-fade-enter-from,
.scroll-jump-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(6px);
}

.sender-resize-handle {
  width: 100%;
  height: 6px;
  cursor: ns-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 2px;
  border-radius: 3px;
  transition: background 0.15s;
}
.sender-resize-handle::before {
  content: '';
  display: block;
  width: 32px;
  height: 3px;
  border-radius: 2px;
  background: var(--border);
  transition: background 0.15s;
}
.sender-resize-handle:hover::before,
.sender-resize-handle:active::before {
  background: var(--border-strong);
}

.agent-sender-wrap {
  width: 100%;
  min-width: 0;
  border: var(--border-width) solid var(--border);
  border-radius: 14px;
  background: var(--panel-bg);
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.08);
  overflow: hidden;
}
html[data-theme='dark'] .agent-sender-wrap {
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
}

.send-queue {
  margin: 0 0 8px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
}
.send-queue-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
.send-queue.collapsed .send-queue-head {
  margin-bottom: 0;
}
.queue-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}
.queue-chevron {
  display: inline-block;
  width: 12px;
  text-align: center;
  transform: rotate(0deg);
  transition: transform 0.15s ease;
  color: var(--text-secondary);
}
.queue-chevron.open {
  transform: rotate(90deg);
}
.queue-clear {
  border: 0;
  background: transparent;
  color: var(--primary);
  font-size: 12px;
  cursor: pointer;
}
.send-queue-item {
  display: grid;
  grid-template-columns: 20px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 4px 0;
}
.queue-index {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: var(--mono);
}
.queue-text {
  font-size: 12.5px;
  color: var(--text-h);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.queue-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.queue-send {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--primary);
  font-size: 11px;
  padding: 2px 8px;
  cursor: pointer;
  line-height: 1.4;
}
.queue-send:hover {
  border-color: var(--primary);
}
.queue-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 2px;
}

.agent-sender {
  width: 100%;
  min-width: 0;
  --tr-sender-bg-color: transparent;
  --tr-sender-text-color: var(--text-h);
  --tr-sender-placeholder-color: color-mix(in srgb, var(--text-muted) 72%, transparent);
}

.agent-sender :deep(.tr-sender) {
  width: 100%;
  box-sizing: border-box;
  border: 0;
  background: transparent;
  box-shadow: none;
  display: flex;
  flex-direction: column;
}

.agent-sender :deep(.tr-sender-content) {
  flex: 1 1 auto;
  overflow-y: auto;
  min-height: var(--sender-content-height, var(--sender-min-height, 40px));
  max-height: var(--sender-content-height, var(--sender-max-height, min(440px, 40vh)));
  height: var(--sender-content-height, auto);
  box-sizing: border-box;
}

.agent-sender :deep(.tr-sender-editor-scroll) {
  min-height: auto;
  height: auto;
  max-height: var(--sender-content-height, var(--sender-max-height, min(440px, 40vh))) !important;
  overflow-y: auto;
}

.agent-sender :deep(.tr-sender-editor-wrapper),
.agent-sender :deep(.tr-sender-editor-content),
.agent-sender :deep(.tr-sender-content .ProseMirror) {
  min-height: auto;
  box-sizing: border-box;
  color: var(--text-h);
}

.agent-sender :deep(.tr-sender-footer) {
  flex: 0 0 auto;
  min-width: 0;
}

.agent-sender :deep(.tr-sender-footer-left) {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
}

.agent-sender :deep(.tr-sender-footer-right) {
  flex: 0 0 auto;
}

.agent-sender :deep(.chat-input-toolbar__think) {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-sender :deep(.tr-sender-content .ProseMirror p.is-editor-empty:first-child::before) {
  color: color-mix(in srgb, var(--text-muted) 72%, transparent);
}

.agent-sender :deep(.tr-sender-submit-button__icon) {
  color: var(--sender-submit-icon);
}

.agent-sender :deep(.tr-sender-submit-button:not(.is-disabled):not(.is-loading):hover .tr-sender-submit-button__icon) {
  color: var(--sender-submit-icon-hover);
}

.agent-sender :deep(.tr-sender-submit-button.is-disabled .tr-sender-submit-button__icon) {
  color: var(--text);
  opacity: 0.45;
}

.agent-sender :deep(.tr-sender-submit-button__cancel) {
  background-color: var(--sender-submit-cancel-bg);
}

.agent-sender :deep(.tr-sender-submit-button__cancel:hover) {
  background-color: var(--sender-submit-cancel-bg-hover);
}

.agent-sender :deep(.tr-sender-submit-button__cancel-icon) {
  color: var(--sender-submit-icon);
}

.agent-sender :deep(.tr-sender-main) {
  align-items: flex-start;
}

.agent-sender-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 4px;
}

.agent-sender-actions :deep(.tr-action-button) {
  color: var(--text);
}

.agent-sender-actions :deep(.tr-action-button:hover:not(:disabled)) {
  color: var(--text-h);
  background: var(--tr-sender-button-hover-bg);
}

.agent-attachments {
  padding: 8px 10px 0;
}

.copy-toast {
  position: fixed;
  top: 48px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 13000;
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--panel-bg);
  color: var(--text-h);
  font-size: 13px;
  font-weight: 500;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  border: var(--border-width) solid var(--border);
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12);
  pointer-events: none;
  white-space: nowrap;
}
html[data-theme='dark'] .copy-toast {
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.45);
}
.copy-toast :deep(.app-icon) {
  color: var(--ok);
}
.toast-fade-enter-active, .toast-fade-leave-active { transition: opacity 0.2s, transform 0.2s; }
.toast-fade-enter-from { opacity: 0; transform: translateX(-50%) translateY(-6px); }
.toast-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(-6px); }

/* @ mention file picker */
.mention-popup {
  position: absolute;
  bottom: calc(100% + 4px);
  left: 12px;
  width: 320px;
  max-width: calc(100% - 24px);
  z-index: 200;
  background: var(--bg-elevated);
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
  overflow: hidden;
  max-height: 300px;
  display: flex;
  flex-direction: column;
}
.mention-tabs {
  display: flex;
  gap: 4px;
  padding: 6px 6px 0;
  border-bottom: var(--border-width) solid var(--border);
  flex-shrink: 0;
}
.mention-tab {
  flex: 1;
  height: 28px;
  border: 0;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.mention-tab:hover {
  color: var(--text-h);
  background: var(--bg-muted);
}
.mention-tab.active {
  color: var(--primary);
  background: var(--primary-soft);
}
.mention-empty {
  margin: 0;
  padding: 14px 12px;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}
.mention-skill-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.mention-skill-desc {
  font-size: 11px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mention-skill-item.selected .mention-name {
  color: var(--primary);
}
.mention-dir-back {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--bg-muted);
}
.mention-back-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11.5px;
  color: var(--text-secondary);
  border: 0;
  background: transparent;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
}
.mention-back-btn:hover { background: var(--border); color: var(--text-h); }
.mention-dir-label {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  font-family: var(--mono);
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mention-list {
  list-style: none;
  margin: 0;
  padding: 4px;
  overflow-y: auto;
  flex: 1;
}
.mention-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text);
  font-size: 13px;
}
.mention-skill-item {
  align-items: flex-start;
}
.mention-item.active { background: var(--primary-soft); color: var(--primary); }
.mention-item.pinned { border-left: 2px solid var(--primary); padding-left: 8px; }
.mention-item:hover { background: var(--bg-muted); }
.mention-item.active:hover { background: var(--primary-soft); }
.mention-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mention-arrow {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
}
.mention-arrow:hover {
  background: var(--border);
  color: var(--text);
}
.mention-fade-enter-active, .mention-fade-leave-active { transition: opacity 0.12s, transform 0.12s; }
.mention-fade-enter-from, .mention-fade-leave-to { opacity: 0; transform: translateY(4px); }

.agent-upload-error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--danger);
}
.agent-upload-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
