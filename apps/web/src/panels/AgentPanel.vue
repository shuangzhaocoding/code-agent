<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, toRef, watch } from 'vue'
import { TrAttachments, TrSender, UploadButton, VoiceButton } from '@opentiny/tiny-robot'
import { useAppStore } from '@/stores/app'
import { rendererFor } from '@/renderers'
import type { Block } from '@/protocol/applyEvent'
import ChatInputToolbar from '@/components/ChatInputToolbar.vue'
import ChatContextUsageButton from '@/components/ChatContextUsageButton.vue'
import ChatContextUsageDialog from '@/components/ChatContextUsageDialog.vue'
import { useChatAttachments } from '@/composables/useChatAttachments'
import { useContextUsagePreview } from '@/composables/useContextUsagePreview'
import {
  attachmentFileMatchers,
  UPLOAD_ACCEPT,
  UPLOAD_MAX_COUNT,
  UPLOAD_MAX_SIZE_MB,
} from '@/utils/fileTypes'

const store = useAppStore()
const scroller = ref<HTMLElement | null>(null)

/* ---- message actions ---- */
const editingMsgId = ref<string | null>(null)  // kept for compat, unused
const editingText = ref('')
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

function startEdit(msg: (typeof store.messages)[0]) {
  const text = msgPlainText(msg)
  // Put text into the sender input box
  draft.value = text
  sender.value?.setContent?.(text)
  nextTick(() => {
    // Focus the sender
    const el = document.querySelector('.agent-sender .ProseMirror') as HTMLElement | null
    el?.focus()
  })
}

function cancelEdit() {
  editingMsgId.value = null
  editingText.value = ''
}

async function submitEdit() {
  const text = editingText.value.trim()
  if (!text) { cancelEdit(); return }
  cancelEdit()
  stick.value = true
  const refs = store.openFile ? [{ type: 'file', path: store.openFile.path }] : []
  store.send(text, refs, [])
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
const timelineInner = ref<HTMLElement | null>(null)
const sender = ref<{ clear: () => void; setContent: (content: string) => void } | null>(null)
const draft = ref('')
const stick = ref(true)
const contextUsageOpen = ref(false)
const uploadError = ref('')
let locking = false
let raf = 0
let followGen = 0
let resizeObs: ResizeObserver | null = null

const {
  attachments,
  addFiles,
  removeAttachment,
  retryUpload,
  clearAttachments,
  getPendingFiles,
  hasUploadingAttachments,
} = useChatAttachments()

const pendingFiles = computed(() => getPendingFiles())

const { preview: contextUsagePreview, loading: contextUsagePreviewLoading } = useContextUsagePreview({
  conversationId: toRef(store, 'conversationId'),
  userContent: draft,
  thinking: toRef(store, 'thinking'),
  mode: toRef(store, 'mode'),
  files: pendingFiles,
})

const contextUsageRingPercent = computed(() => contextUsagePreview.value?.recommendedUsagePercent ?? 0)
const contextUsageRingLevel = computed(() => contextUsagePreview.value?.level ?? 'normal')
const inputBlocked = computed(() => running() || hasUploadingAttachments())

const speechConfig = computed(() => ({
  lang: 'zh-CN',
  continuous: true,
  interimResults: true,
}))

const streamTick = computed(() =>
  store.messages.map((m) => m.blocks.map((b) => `${b.id}:${b.text?.length || 0}:${b.status}`).join('|')).join('/'),
)

function running() {
  return store.runStatus === 'running' || store.runStatus === 'queued'
}

function distanceToBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight
}

function pauseFollow() {
  stick.value = false
  followGen += 1
  if (raf) {
    cancelAnimationFrame(raf)
    raf = 0
  }
}

function jumpToEnd() {
  if (!stick.value) return
  const el = scroller.value
  if (!el) return
  const token = followGen
  const top = Math.max(0, el.scrollHeight - el.clientHeight)
  if (Math.abs(el.scrollTop - top) < 2) return
  locking = true
  el.scrollTop = top
  requestAnimationFrame(() => {
    if (token !== followGen || !stick.value) {
      locking = false
      return
    }
    el.scrollTop = el.scrollHeight
    requestAnimationFrame(() => {
      locking = false
    })
  })
}

function scrollToEnd() {
  if (!stick.value) return
  jumpToEnd()
}

function onScroll() {
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

function followOutput() {
  if (!stick.value) return
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    if (!stick.value) return
    scrollToEnd()
  })
}

onMounted(() => {
  if (timelineInner.value) {
    resizeObs = new ResizeObserver(() => followOutput())
    resizeObs.observe(timelineInner.value)
  }
  followOutput()
})

onBeforeUnmount(() => {
  resizeObs?.disconnect()
  resizeObs = null
  if (raf) cancelAnimationFrame(raf)
})

watch(
  () => store.conversationId,
  async () => {
    stick.value = true
    await nextTick()
    jumpToEnd()
    requestAnimationFrame(jumpToEnd)
  },
)

watch(
  () => [store.conversationId, store.messages.length, store.runStatus, streamTick.value] as const,
  async () => {
    await nextTick()
    followOutput()
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

function onSubmit(text: string) {
  const value = normalizeSubmitText(text || '')
  if (!value || hasUploadingAttachments()) return
  stick.value = true
  const refs = store.openFile ? [{ type: 'file', path: store.openFile.path }] : []
  const files = getPendingFiles()
  store.send(value, refs, files)
  clearSender()
  clearAttachments()
  uploadError.value = ''
  nextTick(() => {
    clearSender()
    scrollToEnd()
  })
}

function onCancel() {
  if (running()) store.stop()
}

function handleFileSelect(files: File[]) {
  uploadError.value = ''
  addFiles(files)
}

function handleUploadError(error: Error) {
  uploadError.value = error.message
}

function handleSpeechError(error: Error) {
  uploadError.value = error.message || '语音识别失败'
}

function openContextUsageDialog() {
  contextUsageOpen.value = true
}
</script>

<template>
  <div class="panel-shell agent">
    <Transition name="toast-fade">
      <div v-if="copyToast" class="copy-toast">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
        已复制
      </div>
    </Transition>
    <header class="panel-head">
      <span class="panel-title">对话</span>
      <span class="spacer" />
      <button v-if="running()" type="button" class="btn" @click="store.stop()">停止</button>
      <button type="button" class="btn btn-primary" @click="store.newChat()">新会话</button>
    </header>
    <div ref="scroller" class="timeline" @scroll="onScroll" @wheel="onWheel" @pointerdown="onPointerDown">
      <div ref="timelineInner" class="timeline-inner">
        <div v-if="!store.messages.length" class="empty">
          描述你想改的代码。可用 Skill、自备模型，刷新后生成会继续。
        </div>
        <article v-for="msg in store.messages" :key="msg.id" :class="['msg-wrap', msg.role]">
          <div v-if="msg.role === 'user'" class="msg-bubble" :class="{ collapsed: !expandedMsgs.has(msg.id) && isLongMsg(msg) }">
            <section v-for="block in msg.blocks" :key="block.id" class="block">
              <component :is="rendererFor(block.type)" :block="block as Block" />
            </section>
          </div>
          <button
            v-if="msg.role === 'user' && isLongMsg(msg)"
            type="button"
            class="msg-expand-btn"
            @click="toggleExpand(msg.id)"
          >{{ expandedMsgs.has(msg.id) ? '收起' : '展开全部' }}</button>
          <template v-else>
            <section v-for="block in msg.blocks" :key="block.id" class="block">
              <component :is="rendererFor(block.type)" :block="block as Block" />
            </section>
          </template>
          <div class="msg-bar" :class="msg.role">
            <span class="msg-time">
              <template v-if="msg.created_at">{{ fmtTime(msg.created_at) }}</template>
              <template v-if="msg.role === 'assistant' && msg.ended_at"> · {{ fmtTime(msg.ended_at) }} · 耗时 {{ fmtDuration(msg) }}</template>
            </span>
            <div class="msg-actions">
              <button v-if="msg.role === 'user'" type="button" class="msg-icon-btn" title="编辑" @click="startEdit(msg)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
              <button type="button" class="msg-icon-btn" title="复制" @click="copyMsg(msg)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              </button>
            </div>
          </div>
        </article>
        <div v-if="running()" class="typing" aria-hidden="true">
          <span class="dots"><i /><i /><i /></span>
        </div>
      </div>
    </div>
    <footer class="agent-footer">
      <div class="agent-sender-wrap">
        <TrSender
          ref="sender"
          v-model="draft"
          class="agent-sender"
          mode="multiple"
          submit-type="enter"
          placeholder="给 Code Agent 下指令…"
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
                tooltip="上传图片"
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
                tooltip="语音输入"
                tooltip-placement="top"
                :speech-config="speechConfig"
                :disabled="inputBlocked"
                @speech-error="handleSpeechError"
              />
            </div>
          </template>
        </TrSender>
      </div>
      <p v-if="uploadError" class="agent-upload-error">{{ uploadError }}</p>
    </footer>

    <ChatContextUsageDialog
      :open="contextUsageOpen"
      :conversation-id="store.conversationId"
      :user-content="draft"
      :thinking="store.thinking"
      :mode="store.mode"
      :files="pendingFiles"
      @close="contextUsageOpen = false"
    />
  </div>
</template>

<style scoped>
.agent { background: var(--bg); position: relative; }
.panel-head { flex-wrap: wrap; }
.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
}
.btn { height: 28px; padding: 0 10px; font-size: 12px; }
.timeline {
  flex: 1;
  overflow-x: hidden;
  overflow-y: scroll;
  overflow-anchor: none;
  padding: 14px 16px 24px;
}
.timeline-inner {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  min-height: min-content;
}
.empty {
  color: var(--text-secondary);
  padding: 32px 8px;
  text-align: center;
  line-height: 1.6;
}
article.msg-wrap.user {
  align-self: flex-end;
  margin-left: auto;
  max-width: min(82%, 560px);
  margin-top: 10px;
  margin-bottom: 10px;
  margin-right: 0;
  overflow-anchor: none;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.msg-bubble {
  background: var(--primary-soft);
  color: var(--text);
  padding: 10px 14px;
  border-radius: 12px 12px 4px 12px;
  width: fit-content;
  max-width: 100%;
  box-sizing: border-box;
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
  background: linear-gradient(transparent, var(--primary-soft));
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
  margin: 10px 28px 10px 0;
  overflow-anchor: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.block + .block { margin-top: 4px; }

/* message action bar */
.msg-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
}
.msg-bar.user {
  flex-direction: row-reverse;
  align-self: flex-end;
}
.msg-time {
  font-size: 11px;
  color: var(--text-secondary);
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
  min-height: 28px;
  padding: 4px 2px 8px;
  color: var(--text-muted);
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
  border-top: var(--border-width) solid var(--border);
  padding: 10px 12px 12px;
  background: var(--panel-bg);
}

.agent-sender-wrap {
  width: 100%;
  min-width: 0;
}

.agent-sender {
  width: 100%;
  min-width: 0;
  --tr-sender-bg-color: var(--code-bg);
  --tr-sender-text-color: var(--text-h);
  --tr-sender-placeholder-color: var(--text);
}

.agent-sender :deep(.tr-sender) {
  width: 100%;
  box-sizing: border-box;
  border: var(--border-width) solid var(--border);
  background: var(--code-bg);
  box-shadow: none;
}

.agent-sender :deep(.tr-sender-footer) {
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

.agent-sender :deep(.tr-sender-content .ProseMirror) {
  min-height: var(--tr-sender-line-height, 26px);
  color: var(--text-h);
}

.agent-sender :deep(.tr-sender-content .ProseMirror p.is-editor-empty:first-child::before) {
  color: var(--text);
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
  position: absolute;
  top: 50px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 6px;
  background: #fff;
  color: #333;
  font-size: 13px;
  font-weight: 500;
  padding: 8px 16px;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12), 0 1px 3px rgba(0,0,0,0.08);
  pointer-events: none;
  white-space: nowrap;
}
.toast-fade-enter-active, .toast-fade-leave-active { transition: opacity 0.2s, transform 0.2s; }
.toast-fade-enter-from { opacity: 0; transform: translateX(-50%) translateY(-6px); }
.toast-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(-6px); }

.agent-upload-error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--danger);
}
</style>
