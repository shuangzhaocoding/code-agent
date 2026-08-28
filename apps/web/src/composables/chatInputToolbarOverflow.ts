import type { ComputedRef, InjectionKey, Ref } from 'vue'
import type { ToolbarSelectOption } from '@/components/ToolbarSelect.vue'

export type ChatInputToolbarOverflowApi = {
  moreHasThinking: ComputedRef<boolean>
  moreHasAdvancedParams: ComputedRef<boolean>
  moreHasMode: ComputedRef<boolean>
  moreHasModel: ComputedRef<boolean>
  moreHasProbe: ComputedRef<boolean>
  thinkingSelectOptions: ComputedRef<ToolbarSelectOption[]>
  thinkingLevel: ComputedRef<string>
  onThinkingChange: (value: string | null) => void
  canTuneParams: ComputedRef<boolean>
  paramsButtonLabel: ComputedRef<string>
  isThinkingActive: ComputedRef<boolean>
  modeOptions: ComputedRef<ToolbarSelectOption[]>
  modelOptions: ComputedRef<ToolbarSelectOption[]>
  mode: ComputedRef<string>
  modelId: ComputedRef<string | null>
  providersEmpty: ComputedRef<boolean>
  openParamsFromMore: (anchor?: HTMLElement | null) => void
  paramsPanelContains: (target: Node) => boolean
  openModelsAndProbeFromMore: () => void
  onModeChange: (value: string | null) => void
  onModelChange: (value: string | null) => void
}

export const chatInputToolbarOverflowKey: InjectionKey<Ref<ChatInputToolbarOverflowApi | null>> =
  Symbol('chatInputToolbarOverflow')
