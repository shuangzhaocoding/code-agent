import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import type { ChatMessage } from '@/protocol/applyEvent'
import {
  buildTimelineSpans,
  trajectoryEntriesForLedger,
} from '@/utils/trajectory'

function structureKey(messages: ChatMessage[]): string {
  return messages
    .map((m) => `${m.id}:${m.blocks.map((b) => `${b.id}:${b.status}`).join(',')}`)
    .join('|')
}

/**
 * Rebuild the trajectory ledger immediately on structural changes
 * (new/completed cards), but throttle token-level updates so the
 * sidebar does not re-layout on every stream delta.
 */
export function useThrottledTrajectory(messages: Ref<ChatMessage[]>, intervalMs = 280) {
  const tick = ref(0)
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastKey = ''

  function bump(immediate: boolean) {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    if (immediate) {
      tick.value += 1
      return
    }
    timer = setTimeout(() => {
      timer = null
      tick.value += 1
    }, intervalMs)
  }

  watch(
    messages,
    (msgs) => {
      const key = structureKey(msgs)
      const structural = key !== lastKey
      lastKey = key
      bump(structural)
    },
    { deep: true, immediate: true },
  )

  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer)
  })

  const entries = computed(() => {
    void tick.value
    return trajectoryEntriesForLedger(messages.value)
  })

  const timelineSpans = computed(() => buildTimelineSpans(entries.value))

  const lastEntry = computed(() => entries.value.at(-1) ?? null)

  return { entries, timelineSpans, lastEntry }
}
