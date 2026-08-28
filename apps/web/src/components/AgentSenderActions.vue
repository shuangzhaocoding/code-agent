<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UploadButton, VoiceButton } from '@opentiny/tiny-robot'
import ChatContextUsageButton from '@/components/ChatContextUsageButton.vue'
import AppIcon from '@/components/AppIcon.vue'
import ToolbarSelect from '@/components/ToolbarSelect.vue'
import { chatInputToolbarOverflowKey } from '@/composables/chatInputToolbarOverflow'
import { useSenderFooterBreakpoints } from '@/composables/useSenderFooterBreakpoints'
import type { ContextUsageLevel } from '@/types/contextUsage'

const props = defineProps<{
  contextPercent: number
  contextLevel: ContextUsageLevel
  contextLoading: boolean
  contextDisabled: boolean
  inputBlocked: boolean
  speechConfig: Record<string, unknown>
  uploadAccept: string
  uploadMaxSize: number
  uploadMaxCount: number
}>()

const emit = defineEmits<{
  contextClick: []
  fileSelect: [files: File[]]
  uploadError: [error: Error]
  speechError: [error: Error]
}>()

const { t } = useI18n()
const toolbarOverflowRef = inject(chatInputToolbarOverflowKey, null)
const toolbarOverflow = computed(() => toolbarOverflowRef?.value ?? null)
const {
  showContextInline,
  showVoiceInline,
  showUploadInline,
  moreHasContext,
  moreHasVoice,
  moreHasUpload,
  showMore,
} = useSenderFooterBreakpoints()

const moreOpen = ref(false)
const moreReady = ref(false)
const moreBtn = ref<HTMLElement | null>(null)
const morePanel = ref<HTMLElement | null>(null)
const moreStyle = ref<Record<string, string>>({})

const hasToolbarOverflow = computed(() => {
  const api = toolbarOverflow.value
  if (!api) return false
  return (
    api.moreHasThinking.value ||
    api.moreHasAdvancedParams.value ||
    api.moreHasMode.value ||
    api.moreHasModel.value ||
    api.moreHasProbe.value
  )
})

const hasActionsOverflow = computed(
  () => moreHasContext.value || moreHasVoice.value || moreHasUpload.value,
)

function placeMorePanel() {
  const el = moreBtn.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const width = 240
  let left = rect.right - width
  if (left < 8) left = 8
  if (left + width > window.innerWidth - 8) left = window.innerWidth - width - 8
  moreStyle.value = {
    position: 'fixed',
    left: `${left}px`,
    top: `${Math.max(8, rect.top)}px`,
    transform: 'translateY(calc(-100% - 8px))',
    width: `${width}px`,
    zIndex: '1000',
  }
}

function openMore() {
  placeMorePanel()
  moreReady.value = false
  moreOpen.value = true
  void nextTick(() => {
    placeMorePanel()
    moreReady.value = true
  })
}

function closeMore() {
  moreOpen.value = false
  moreReady.value = false
}

function toggleMore() {
  if (moreOpen.value) closeMore()
  else openMore()
}

function onDocPointer(e: PointerEvent) {
  const target = e.target as Node
  if (moreBtn.value?.contains(target) || morePanel.value?.contains(target)) return
  if (toolbarOverflow.value?.paramsPanelContains(target)) return
  closeMore()
}

watch(showMore, (visible) => {
  if (!visible) closeMore()
})

onMounted(() => document.addEventListener('pointerdown', onDocPointer))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocPointer))

function onContextClick() {
  closeMore()
  emit('contextClick')
}

function onFileSelect(files: File[]) {
  closeMore()
  emit('fileSelect', files)
}

function onAdvancedParamsFromMore(event: MouseEvent) {
  const api = toolbarOverflow.value
  if (!api) return
  api.openParamsFromMore(event.currentTarget as HTMLElement)
}

function onProbeFromMore() {
  const api = toolbarOverflow.value
  if (!api) return
  closeMore()
  api.openModelsAndProbeFromMore()
}

function activateMoreRowAction(row: EventTarget | null) {
  const el = row as HTMLElement | null
  el?.querySelector<HTMLElement>('.tr-action-button')?.click()
}
</script>

<template>
  <div class="agent-sender-actions">
    <ChatContextUsageButton
      v-if="showContextInline"
      class="action-inline"
      :percent="contextPercent"
      :level="contextLevel"
      :loading="contextLoading"
      :disabled="contextDisabled"
      @click="emit('contextClick')"
    />
    <UploadButton
      v-if="showUploadInline"
      class="action-inline"
      :tooltip="t('chat.uploadImage')"
      tooltip-placement="top"
      multiple
      :max-size="uploadMaxSize"
      :max-count="uploadMaxCount"
      :accept="uploadAccept"
      :disabled="inputBlocked"
      @select="emit('fileSelect', $event)"
      @error="emit('uploadError', $event)"
    />
    <VoiceButton
      v-if="showVoiceInline"
      class="action-inline"
      :tooltip="t('chat.voiceInput')"
      tooltip-placement="top"
      :speech-config="speechConfig"
      :disabled="inputBlocked"
      @speech-error="emit('speechError', $event)"
    />

    <button
      v-if="showMore"
      ref="moreBtn"
      type="button"
      class="ghost-icon-btn more-btn"
      :title="t('chat.moreActions')"
      :aria-label="t('chat.moreActions')"
      :aria-expanded="moreOpen"
      @click.stop="toggleMore"
    >
      <AppIcon name="more" :size="16" :stroke-width="1.75" />
    </button>

    <Teleport to="body">
      <div
        v-if="moreOpen"
        ref="morePanel"
        class="more-panel"
        :class="{ ready: moreReady }"
        :style="moreStyle"
        @pointerdown.stop
      >
        <template v-if="toolbarOverflow && hasToolbarOverflow">
          <div v-if="toolbarOverflow.moreHasThinking.value" class="more-item more-item-control">
            <ToolbarSelect
              :model-value="toolbarOverflow.thinkingLevel.value"
              :options="toolbarOverflow.thinkingSelectOptions.value"
              :min-width="72"
              @update:model-value="toolbarOverflow.onThinkingChange"
            />
          </div>
          <button
            v-if="toolbarOverflow.moreHasAdvancedParams.value"
            type="button"
            class="more-item"
            @click="onAdvancedParamsFromMore"
          >
            <AppIcon name="tune" :size="16" :stroke-width="1.75" />
            <span class="more-label">{{ t('chat.params') }}</span>
          </button>
          <div v-if="toolbarOverflow.moreHasMode.value" class="more-item more-item-control">
            <ToolbarSelect
              :model-value="toolbarOverflow.mode.value"
              :options="toolbarOverflow.modeOptions.value"
              :min-width="72"
              @update:model-value="toolbarOverflow.onModeChange"
            />
          </div>
          <div v-if="toolbarOverflow.moreHasModel.value" class="more-item more-item-control">
            <ToolbarSelect
              :model-value="toolbarOverflow.modelId.value"
              :options="toolbarOverflow.modelOptions.value"
              :placeholder="t('chat.selectModel')"
              :min-width="96"
              searchable
              :search-placeholder="t('chat.searchModel')"
              @update:model-value="toolbarOverflow.onModelChange"
            />
          </div>
          <button
            v-if="toolbarOverflow.moreHasProbe.value"
            type="button"
            class="more-item"
            :disabled="toolbarOverflow.providersEmpty.value"
            @click="onProbeFromMore"
          >
            <AppIcon name="refresh" :size="16" :stroke-width="1.75" />
            <span class="more-label">{{ t('chat.openModels') }}</span>
          </button>
        </template>

        <div
          v-if="toolbarOverflow && hasToolbarOverflow && hasActionsOverflow"
          class="more-divider"
          role="separator"
        />

        <button
          v-if="moreHasContext"
          type="button"
          class="more-item"
          :disabled="contextDisabled"
          @click="onContextClick"
        >
          <ChatContextUsageButton
            :percent="contextPercent"
            :level="contextLevel"
            :loading="contextLoading"
            :disabled="contextDisabled"
            @click.stop="onContextClick"
          />
          <span class="more-label">{{ t('usage.title') }}</span>
          <span class="more-meta">{{ contextPercent.toFixed(1) }}%</span>
        </button>
        <div
          v-if="moreHasUpload"
          role="button"
          tabindex="0"
          class="more-item more-item-action"
          :class="{ 'is-disabled': inputBlocked }"
          @click="!inputBlocked && activateMoreRowAction($event.currentTarget)"
          @keydown.enter.prevent="!inputBlocked && activateMoreRowAction($event.currentTarget)"
        >
          <UploadButton
            class="more-item-native"
            :tooltip="t('chat.uploadImage')"
            tooltip-placement="left"
            multiple
            :max-size="uploadMaxSize"
            :max-count="uploadMaxCount"
            :accept="uploadAccept"
            :disabled="inputBlocked"
            @select="onFileSelect"
            @error="emit('uploadError', $event)"
          />
          <span class="more-label">{{ t('chat.uploadImage') }}</span>
        </div>
        <div
          v-if="moreHasVoice"
          role="button"
          tabindex="0"
          class="more-item more-item-action"
          :class="{ 'is-disabled': inputBlocked }"
          @click="!inputBlocked && activateMoreRowAction($event.currentTarget)"
          @keydown.enter.prevent="!inputBlocked && activateMoreRowAction($event.currentTarget)"
        >
          <VoiceButton
            class="more-item-native"
            :tooltip="t('chat.voiceInput')"
            tooltip-placement="left"
            :speech-config="speechConfig"
            :disabled="inputBlocked"
            @speech-error="emit('speechError', $event)"
          />
          <span class="more-label">{{ t('chat.voiceInput') }}</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.agent-sender-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 10px;
}

.agent-sender-actions :deep(.action-inline.tr-action-button) {
  width: auto;
  min-width: 0;
  height: var(--ghost-btn-height);
  padding: var(--ghost-btn-padding);
  border: 0;
  border-radius: var(--ghost-btn-radius);
  background: transparent;
  color: var(--text-h);
  transition: opacity 0.15s ease;
}

.agent-sender-actions :deep(.action-inline.tr-action-button:hover:not(:disabled)) {
  color: var(--text-h);
  background: transparent;
  opacity: var(--ghost-hover-opacity);
}

.more-panel {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}

.more-panel.ready {
  opacity: 1;
  pointer-events: auto;
}

html[data-theme='dark'] .more-panel {
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.45);
}

.more-divider {
  height: 0;
  margin: 4px 0;
  border-top: var(--border-width) solid var(--border);
}

.more-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 34px;
  padding: 4px 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-h);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.12s ease;
}

.more-item:hover:not(:disabled) {
  background: var(--code-bg);
}

.more-item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.more-item-control {
  cursor: default;
  padding: 2px 4px;
}

.more-item-action {
  cursor: pointer;
}

.more-item-action.is-disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.more-item-native {
  pointer-events: none;
  flex-shrink: 0;
}

.more-item-control:hover {
  background: var(--code-bg);
}

.more-item-control :deep(.toolbar-select) {
  width: 100%;
  min-width: 0;
}

.more-label {
  flex: 1;
  min-width: 0;
  line-height: 1.2;
}

.more-meta {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.more-item :deep(.more-item-native.tr-action-button) {
  width: auto;
  min-width: 0;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-h);
  pointer-events: none;
}

.more-item :deep(.tr-action-button:hover:not(:disabled)) {
  background: transparent;
  opacity: 1;
}
</style>
