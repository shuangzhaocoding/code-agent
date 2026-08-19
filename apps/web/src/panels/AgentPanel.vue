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

function onSubmit(text: string) {
  const value = text?.trim()
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
        <article v-for="msg in store.messages" :key="msg.id" :class="msg.role">
          <section v-for="block in msg.blocks" :key="block.id" class="block">
            <component :is="rendererFor(block.type)" :block="block as Block" />
          </section>
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
.agent { background: var(--bg); }
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
  min-height: min-content;
}
.empty {
  color: var(--text-secondary);
  padding: 32px 8px;
  text-align: center;
  line-height: 1.6;
}
article.user {
  align-self: flex-end;
  max-width: min(82%, 560px);
  width: fit-content;
  margin: 10px 0 10px 40px;
  background: var(--primary-soft);
  color: var(--text);
  padding: 10px 14px;
  border-radius: 12px 12px 4px 12px;
  overflow-anchor: none;
}
article.assistant {
  align-self: stretch;
  margin: 10px 28px 10px 0;
  overflow-anchor: none;
}
.block + .block { margin-top: 4px; }
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

.agent-upload-error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--danger);
}
</style>
