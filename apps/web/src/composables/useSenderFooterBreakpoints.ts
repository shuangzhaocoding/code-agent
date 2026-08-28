import { computed } from 'vue'
import { useSenderFooterLayout } from '@/composables/useSenderLayoutWidth'

function estimatedRightReserve(footerWidth: number) {
  let reserve = 52
  if (footerWidth >= 340) reserve += 34
  if (footerWidth >= 300) reserve += 34
  if (footerWidth >= 260) reserve += 34
  else if (footerWidth >= 200) reserve += 34
  return reserve + 12
}

export function useSenderFooterBreakpoints() {
  const { footerWidth, footerLeftWidth, footerRightWidth } = useSenderFooterLayout()

  const layoutReady = computed(
    () => Number.isFinite(footerWidth.value) && footerWidth.value > 0 && footerWidth.value < 100_000,
  )

  const leftBudget = computed(() => {
    if (!layoutReady.value) return Number.POSITIVE_INFINITY
    const measured = footerWidth.value - footerRightWidth.value - 12
    const estimated = footerWidth.value - estimatedRightReserve(footerWidth.value)
    return Math.max(0, Math.max(measured, estimated))
  })

  const showThinkingInline = computed(() => !layoutReady.value || leftBudget.value >= 76)
  const showModeInline = computed(() => !layoutReady.value || leftBudget.value >= 152)
  const showModelInline = computed(() => !layoutReady.value || leftBudget.value >= 248)
  const showProbeInline = computed(() => !layoutReady.value || leftBudget.value >= 280)

  const showUploadInline = computed(() => !layoutReady.value || footerWidth.value >= 260)
  const showVoiceInline = computed(() => !layoutReady.value || footerWidth.value >= 300)
  const showContextInline = computed(() => !layoutReady.value || footerWidth.value >= 340)

  const moreHasThinking = computed(() => layoutReady.value && !showThinkingInline.value)
  const moreHasMode = computed(() => layoutReady.value && !showModeInline.value)
  const moreHasModel = computed(() => layoutReady.value && !showModelInline.value)
  const moreHasProbe = computed(() => layoutReady.value && !showProbeInline.value)

  const moreHasUpload = computed(() => layoutReady.value && !showUploadInline.value)
  const moreHasVoice = computed(() => layoutReady.value && !showVoiceInline.value)
  const moreHasContext = computed(() => layoutReady.value && !showContextInline.value)

  const hasAnyOverflow = computed(
    () =>
      moreHasThinking.value ||
      moreHasMode.value ||
      moreHasModel.value ||
      moreHasProbe.value ||
      moreHasUpload.value ||
      moreHasVoice.value ||
      moreHasContext.value,
  )

  const showMore = computed(() => layoutReady.value && footerWidth.value >= 200 && hasAnyOverflow.value)

  return {
    footerWidth,
    footerLeftWidth,
    footerRightWidth,
    leftBudget,
    layoutReady,
    showProbeInline,
    showModelInline,
    showModeInline,
    showThinkingInline,
    showContextInline,
    showVoiceInline,
    showUploadInline,
    moreHasProbe,
    moreHasModel,
    moreHasMode,
    moreHasThinking,
    moreHasContext,
    moreHasVoice,
    moreHasUpload,
    hasAnyOverflow,
    showMore,
  }
}
