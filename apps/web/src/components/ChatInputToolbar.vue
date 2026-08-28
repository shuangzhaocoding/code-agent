<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import ToolbarSelect, { type ToolbarSelectOption } from '@/components/ToolbarSelect.vue'
import AppIcon from '@/components/AppIcon.vue'
import { chatInputToolbarOverflowKey, type ChatInputToolbarOverflowApi } from '@/composables/chatInputToolbarOverflow'
import { useSenderFooterBreakpoints } from '@/composables/useSenderFooterBreakpoints'
import { type ThinkingLevel } from '@/types/thinking'
import type { LlmModel, LlmProvider, ThinkingOption } from '@/types/llm'

const { t } = useI18n()
const store = useAppStore()
const {
  leftBudget,
  showProbeInline,
  showModelInline,
  showModeInline,
  showThinkingInline,
  moreHasProbe,
  moreHasModel,
  moreHasMode,
  moreHasThinking,
} = useSenderFooterBreakpoints()
const paramsOpen = ref(false)
const paramsReady = ref(false)
const paramsBtn = ref<HTMLElement | null>(null)
const paramsBtnMore = ref<HTMLElement | null>(null)
const paramsAnchorRect = ref<DOMRect | null>(null)
const paramsPanel = ref<HTMLElement | null>(null)
const paramsStyle = ref<Record<string, string>>({})
type SavedModelParams = {
  thinking?: ThinkingLevel
  temperature?: number
  top_p?: number
}

const PARAMS_KEY = 'ca.model_params_by_model'
const paramsByModel = ref<Record<string, SavedModelParams>>(loadParamsByModel())

function loadParamsByModel(): Record<string, SavedModelParams> {
  try {
    const raw = localStorage.getItem(PARAMS_KEY) || localStorage.getItem('ca.thinking_by_model')
    const parsed = raw ? JSON.parse(raw) : {}
    if (!parsed || typeof parsed !== 'object') return {}
    const out: Record<string, SavedModelParams> = {}
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === 'string') out[id] = { thinking: value as ThinkingLevel }
      else if (value && typeof value === 'object') out[id] = value as SavedModelParams
    }
    return out
  } catch {
    return {}
  }
}

function persistModelParams(modelId: string, patch: SavedModelParams) {
  const next: SavedModelParams = { ...(paramsByModel.value[modelId] || {}) }
  for (const [key, value] of Object.entries(patch) as [keyof SavedModelParams, unknown][]) {
    if (value == null) delete next[key]
    else (next as Record<string, unknown>)[key] = value
  }
  paramsByModel.value = { ...paramsByModel.value, [modelId]: next }
  localStorage.setItem(PARAMS_KEY, JSON.stringify(paramsByModel.value))
}

function snapshotCurrentParams(modelId: string) {
  persistModelParams(modelId, {
    thinking: store.thinkingLevel,
    ...(store.sampling.temperature != null ? { temperature: store.sampling.temperature } : {}),
  })
}

const modeOptions = computed<ToolbarSelectOption[]>(() => [
  { value: 'ask', label: 'Ask', description: t('chat.modeAsk'), icon: 'chat', accent: '#0891b2' },
  { value: 'agent', label: 'Agent', description: t('chat.modeAgent'), icon: 'zap', accent: 'var(--primary)' },
  { value: 'plan', label: 'Plan', description: t('chat.modePlan'), icon: 'list', accent: '#d97706' },
])

function isProbed(model: LlmModel) {
  return model.availability != null && model.availability.ok != null
}

function isAvailable(model: LlmModel) {
  return model.availability?.ok === true
}

const allModels = computed(() =>
  store.providers.flatMap((provider: LlmProvider) =>
    (provider.models || []).map((model: LlmModel) => ({ provider, model })),
  ),
)

const visibleModels = computed(() => {
  const rows = allModels.value
  const probed = rows.some(({ model }) => isProbed(model))
  if (!probed) return rows
  return rows.filter(({ model }) => isAvailable(model) || model.id === store.modelId)
})

const selectedModel = computed(() => visibleModels.value.find(({ model }) => model.id === store.modelId)?.model)

const modelOptions = computed(() =>
  visibleModels.value.map(({ provider, model }) => {
    const probed = isProbed(model)
    const ok = isAvailable(model)
    return {
      value: model.id,
      label: model.display_name,
      description: provider.name,
      icon: 'chip',
      group: provider.name,
      badge: !probed ? t('chat.badgeUnknown') : ok ? t('chat.badgeOk') : t('chat.badgeFail'),
      badgeKind: !probed ? 'unknown' : ok ? 'ok' : 'fail',
    } satisfies ToolbarSelectOption
  }),
)

const thinkingLabels = computed<Record<string, { label: string; description: string }>>(() => ({
  off: { label: t('thinking.off.label'), description: t('thinking.off.description') },
  low: { label: t('thinking.low.label'), description: t('thinking.low.description') },
  medium: { label: t('thinking.medium.label'), description: t('thinking.medium.description') },
  high: { label: t('thinking.high.label'), description: t('thinking.high.description') },
}))

const thinkingOptions = computed(() => {
  const model = selectedModel.value
  const spec = model?.capabilities?.thinking
  if (!spec?.supported) return []
  const raw = spec.levels?.length ? spec.levels : ['off', 'low', 'medium', 'high']
  return raw.map((item: string | ThinkingOption) => {
    const value = typeof item === 'string' ? item : item.value
    const meta = thinkingLabels.value[value] || { label: value, description: '' }
    return {
      value,
      label: typeof item === 'string' ? meta.label : item.label || meta.label,
      description: typeof item === 'string' ? meta.description : item.description || meta.description,
    }
  })
})

const temperatureSpec = computed(() => {
  const spec = selectedModel.value?.capabilities?.temperature
  return spec?.supported ? spec : null
})

const topPSpec = computed(() => {
  const spec = selectedModel.value?.capabilities?.top_p
  return spec?.supported ? spec : null
})

const thinkingSelectOptions = computed<ToolbarSelectOption[]>(() =>
  thinkingOptions.value.map((item) => ({
    value: item.value,
    label: item.label,
    description: item.description,
    icon: 'atom',
  })),
)

const showAdvancedParams = computed(() => Boolean(temperatureSpec.value || topPSpec.value))

const showAdvancedParamsInline = computed(
  () => showAdvancedParams.value && leftBudget.value >= (thinkingOptions.value.length ? 236 : 76),
)

const canTuneParams = computed(() => Boolean(thinkingOptions.value.length || showAdvancedParams.value))

const thinkingLabel = computed(() => {
  if (!thinkingOptions.value.length) return ''
  const current = thinkingOptions.value.find((item: { value: string; label: string }) => item.value === store.thinkingLevel)
  return current?.label || t('thinking.fallback')
})

const paramsButtonLabel = computed(() => thinkingLabel.value || t('chat.params'))

const isThinkingActive = computed(() => store.thinkingLevel !== 'off' && Boolean(thinkingLabel.value))

watch(
  visibleModels,
  (rows) => {
    if (!rows.length) return
    if (rows.some(({ model }) => model.id === store.modelId)) return
    const available = rows.find(({ model }) => isAvailable(model)) || rows[0]
    if (available) store.modelId = available.model.id
  },
  { immediate: true },
)

let applyingModelParams = false

function allowedThinking(model: LlmModel): string[] {
  const spec = model.capabilities?.thinking
  if (!spec?.supported) return []
  const raw = spec.levels?.length ? spec.levels : ['off', 'low', 'medium', 'high']
  return raw.map((item) => (typeof item === 'string' ? item : item.value))
}

function thinkingForModel(model: LlmModel | undefined): ThinkingLevel {
  if (!model) return store.thinkingLevel
  const allowed = allowedThinking(model)
  if (!allowed.length) return store.thinkingLevel
  const saved = paramsByModel.value[model.id]?.thinking
  if (saved && allowed.includes(saved)) return saved
  if (allowed.includes(store.thinkingLevel)) return store.thinkingLevel
  return (allowed[0] as ThinkingLevel) || store.thinkingLevel
}

function applyModelParams(model: LlmModel | undefined) {
  applyingModelParams = true
  const saved = model ? paramsByModel.value[model.id] : undefined
  const allowed = model ? allowedThinking(model) : []
  if (allowed.length) store.thinkingLevel = thinkingForModel(model)
  const tempSpec = model?.capabilities?.temperature
  if (tempSpec?.supported) {
    if (saved?.temperature != null) store.sampling.temperature = Number(saved.temperature)
    else if (store.sampling.temperature == null) {
      store.sampling.temperature = Number(model?.params?.temperature ?? tempSpec.default ?? 0.2)
    }
  }
  if (model && saved?.top_p != null) {
    if (!model.params) model.params = {}
    model.params.top_p = saved.top_p
  }
  queueMicrotask(() => {
    applyingModelParams = false
  })
}

watch(
  () => store.modelId,
  (id, prevId) => {
    if (prevId && prevId !== id) snapshotCurrentParams(prevId)
    const model = visibleModels.value.find(({ model }) => model.id === id)?.model
    applyModelParams(model)
  },
  { immediate: true },
)

watch(
  () => store.thinkingLevel,
  (level) => {
    if (applyingModelParams) return
    if (store.modelId) persistModelParams(store.modelId, { thinking: level })
  },
)

function placeParamsPanel() {
  const el = paramsBtn.value ?? paramsBtnMore.value
  const rect = el?.getBoundingClientRect() ?? paramsAnchorRect.value
  if (!rect) return
  const width = 280
  let left = rect.left
  if (left + width > window.innerWidth - 8) left = window.innerWidth - width - 8
  paramsStyle.value = {
    position: 'fixed',
    left: `${Math.max(8, left)}px`,
    top: `${Math.max(8, rect.top)}px`,
    transform: 'translateY(calc(-100% - 8px))',
    width: `${width}px`,
    zIndex: '1000',
  }
}

function openParams() {
  if (!showAdvancedParams.value) return
  placeParamsPanel()
  paramsReady.value = false
  paramsOpen.value = true
  void nextTick(() => {
    placeParamsPanel()
    paramsReady.value = true
  })
}

function closeParams() {
  paramsOpen.value = false
  paramsReady.value = false
  paramsAnchorRect.value = null
}

function toggleParams() {
  if (paramsOpen.value) closeParams()
  else openParams()
}

function openParamsFromMore(anchor?: HTMLElement | null) {
  if (anchor) {
    paramsAnchorRect.value = anchor.getBoundingClientRect()
    paramsBtnMore.value = null
  }
  void nextTick(() => openParams())
}

function onDocPointer(e: PointerEvent) {
  const target = e.target as Node
  if (
    paramsBtn.value?.contains(target) ||
    paramsBtnMore.value?.contains(target) ||
    paramsPanel.value?.contains(target)
  ) {
    return
  }
  closeParams()
}

onMounted(() => document.addEventListener('pointerdown', onDocPointer))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocPointer))

function onThinkingChange(value: string | null) {
  if (!value) return
  store.thinkingLevel = value as ThinkingLevel
}

async function patchModelParams(patch: Record<string, number | null>) {
  const model = selectedModel.value
  if (!model) return
  const next: Record<string, number> = { ...(model.params || {}) }
  for (const [key, value] of Object.entries(patch)) {
    if (value == null) delete next[key]
    else next[key] = value
  }
  try {
    await api(`/api/llm/models/${model.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ params: next }),
    })
    model.params = next
  } catch {
    /* keep local override */
  }
}

async function onTemperatureInput(raw: string) {
  const next = Number(raw)
  store.sampling.temperature = next
  if (store.modelId) persistModelParams(store.modelId, { temperature: next })
  await patchModelParams({ temperature: next })
}

const topPEnabled = computed(() => {
  const value = selectedModel.value?.params?.top_p
  return value != null && value < 1
})

async function onTopPEnabled(on: boolean) {
  const model = selectedModel.value
  if (!model) return
  if (!on) {
    persistModelParams(model.id, { top_p: undefined })
    await patchModelParams({ top_p: null })
    return
  }
  await onTopPInput(String(Math.min(0.95, topPSpec.value?.default ?? 0.9)))
}

async function onTopPInput(raw: string) {
  const next = Math.min(0.99, Math.max(0.05, Number(raw)))
  const model = selectedModel.value
  if (!model) return
  if (!model.params) model.params = {}
  model.params.top_p = next
  persistModelParams(model.id, { top_p: next })
  await patchModelParams({ top_p: next })
}

function onModelChange(id: string | null) {
  store.modelId = id
}

function openModelsAndProbe() {
  store.pendingModelProbe = true
  window.dispatchEvent(new CustomEvent('ca-open-models'))
}

const toolbarOverflowRef = inject(chatInputToolbarOverflowKey, null)

onMounted(() => {
  if (!toolbarOverflowRef) return
  toolbarOverflowRef.value = {
    moreHasThinking: computed(() => moreHasThinking.value && thinkingOptions.value.length > 0),
    moreHasAdvancedParams: computed(() => showAdvancedParams.value && !showAdvancedParamsInline.value),
    moreHasMode,
    moreHasModel,
    moreHasProbe,
    thinkingSelectOptions,
    thinkingLevel: computed(() => store.thinkingLevel),
    onThinkingChange,
    canTuneParams,
    paramsButtonLabel,
    isThinkingActive,
    modeOptions,
    modelOptions,
    mode: computed(() => store.mode),
    modelId: computed(() => store.modelId),
    providersEmpty: computed(() => !store.providers.length),
    openParamsFromMore,
    paramsPanelContains: (target) => paramsPanel.value?.contains(target) ?? false,
    openModelsAndProbeFromMore: openModelsAndProbe,
    onModeChange: (value) => {
      store.mode = value as typeof store.mode
    },
    onModelChange,
  } as ChatInputToolbarOverflowApi
})

onBeforeUnmount(() => {
  if (toolbarOverflowRef) toolbarOverflowRef.value = null
})
</script>

<template>
  <div class="chat-input-toolbar">
    <ToolbarSelect
      v-if="thinkingOptions.length && showThinkingInline"
      :model-value="store.thinkingLevel"
      :options="thinkingSelectOptions"
      :min-width="72"
      @update:model-value="onThinkingChange"
    />

    <button
      v-if="showAdvancedParams && showAdvancedParamsInline"
      ref="paramsBtn"
      type="button"
      class="ghost-btn params-btn"
      :class="{ open: paramsOpen }"
      :title="t('chat.params')"
      @click.stop="toggleParams"
    >
      <AppIcon name="tune" :size="16" :stroke-width="1.75" />
      <span class="params-text">{{ t('chat.params') }}</span>
    </button>

    <ToolbarSelect
      v-if="showModeInline"
      :model-value="store.mode"
      :options="modeOptions"
      :min-width="72"
      @update:model-value="store.mode = $event as typeof store.mode"
    />

    <ToolbarSelect
      v-if="showModelInline"
      :model-value="store.modelId"
      :options="modelOptions"
      :placeholder="t('chat.selectModel')"
      :min-width="96"
      grow
      searchable
      :search-placeholder="t('chat.searchModel')"
      @update:model-value="onModelChange"
    />
    <button
      v-if="showProbeInline"
      type="button"
      class="ghost-icon-btn probe-btn"
      :disabled="!store.providers.length"
      :title="t('chat.openModels')"
      @click="openModelsAndProbe"
    >
      <AppIcon name="refresh" :size="16" :stroke-width="1.75" />
    </button>

    <Teleport to="body">
      <div
        v-if="paramsOpen"
        ref="paramsPanel"
        class="params-panel"
        :class="{ ready: paramsReady }"
        :style="paramsStyle"
        @pointerdown.stop
      >
        <p class="params-title">{{ t('chat.paramsTitle') }}</p>
        <section v-if="temperatureSpec" class="params-block">
          <span class="params-label">{{ t('chat.temperature', { value: store.sampling.temperature ?? temperatureSpec.default ?? 0.2 }) }}</span>
          <input
            type="range"
            class="params-range"
            :min="temperatureSpec.min ?? 0"
            :max="temperatureSpec.max ?? 2"
            :step="temperatureSpec.step ?? 0.1"
            :value="store.sampling.temperature ?? temperatureSpec.default ?? 0.2"
            @input="onTemperatureInput(($event.target as HTMLInputElement).value)"
          />
        </section>
        <section v-if="topPSpec" class="params-block">
          <label class="params-label params-toggle">
            <input type="checkbox" :checked="topPEnabled" @change="onTopPEnabled(($event.target as HTMLInputElement).checked)" />
            {{ t('chat.sendTopP') }}
          </label>
          <template v-if="topPEnabled">
            <span class="params-hint">{{ selectedModel?.params?.top_p }}</span>
            <input
              type="range"
              class="params-range"
              :min="topPSpec.min ?? 0.05"
              :max="0.99"
              :step="topPSpec.step ?? 0.05"
              :value="selectedModel?.params?.top_p ?? 0.9"
              @input="onTopPInput(($event.target as HTMLInputElement).value)"
            />
          </template>
          <p v-else class="params-hint">{{ t('chat.topPHint') }}</p>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.chat-input-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: nowrap;
  min-width: 0;
  overflow: hidden;
}
.chat-input-toolbar :deep(.trigger-desc) {
  display: none;
}
.chat-input-toolbar :deep(.option-badge) {
  display: none;
}
.chat-input-toolbar :deep(.toolbar-select) {
  min-width: 0;
}
.chat-input-toolbar :deep(.toolbar-select-trigger) {
  padding: 0 2px;
}
.params-btn.open {
  opacity: var(--ghost-hover-opacity);
}
.params-text {
  line-height: 1;
  white-space: nowrap;
}
.params-panel {
  padding: 10px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}
.params-panel.ready {
  opacity: 1;
  pointer-events: auto;
}
.params-title {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.params-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.params-block + .params-block {
  margin-top: 10px;
}
.params-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}
.params-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.params-hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-muted);
}
.params-range {
  width: 100%;
  accent-color: var(--primary);
}
</style>
