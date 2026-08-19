import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { fetchContextUsage } from '@/services/contextUsageService'
import type { ContextUsageLevel, PendingFilePayload } from '@/types/contextUsage'
import type { ThinkingLevel } from '@/types/thinking'

export interface ContextUsagePreview {
  usagePercent: number
  recommendedUsagePercent: number
  level: ContextUsageLevel
  totalEstimatedInput: number
}

interface UseContextUsagePreviewOptions {
  conversationId: Ref<string | null>
  userContent: Ref<string>
  thinkingLevel: Ref<ThinkingLevel>
  mode: Ref<string>
  files: Ref<PendingFilePayload[]>
  enabled?: Ref<boolean>
  debounceMs?: number
}

export function useContextUsagePreview(options: UseContextUsagePreviewOptions) {
  const preview = ref<ContextUsagePreview | null>(null)
  const loading = ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let abortController: AbortController | null = null

  async function loadPreview() {
    if (options.enabled?.value === false) return
    if (!options.conversationId.value) {
      preview.value = null
      return
    }

    abortController?.abort()
    abortController = new AbortController()
    loading.value = true

    try {
      const data = await fetchContextUsage({
        conversationId: options.conversationId.value,
        userContent: options.userContent.value.trim(),
        thinkingLevel: options.thinkingLevel.value,
        thinking: options.thinkingLevel.value !== 'off',
        mode: options.mode.value,
        files: options.files.value,
        signal: abortController.signal,
      })
      preview.value = {
        usagePercent: data.usagePercent,
        recommendedUsagePercent: data.recommendedUsagePercent,
        level: data.level,
        totalEstimatedInput: data.totalEstimatedInput,
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      preview.value = null
    } finally {
      loading.value = false
    }
  }

  function schedulePreview() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      void loadPreview()
    }, options.debounceMs ?? 600)
  }

  watch(
    [
      options.conversationId,
      options.userContent,
      options.thinkingLevel,
      options.mode,
      options.files,
      () => options.enabled?.value,
    ],
    schedulePreview,
    { deep: true, immediate: true },
  )

  onBeforeUnmount(() => {
    if (debounceTimer) clearTimeout(debounceTimer)
    abortController?.abort()
  })

  return { preview, loading }
}
