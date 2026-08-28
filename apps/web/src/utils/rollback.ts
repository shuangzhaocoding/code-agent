import type { ChatMessage } from '@/protocol/applyEvent'

export type RollbackMode = 'to' | 'before'

function assistantReplySortKey(anchor: ChatMessage, messages: ChatMessage[]): number | null {
  let seenAnchor = false
  for (const msg of messages) {
    if (msg.id === anchor.id) {
      seenAnchor = true
      continue
    }
    if (!seenAnchor) continue
    if (msg.role === 'user') return null
    if (msg.role === 'assistant') return msg.sort_key ?? null
  }
  return null
}

export function rollbackCutoffSortKey(anchor: ChatMessage, messages: ChatMessage[], mode: RollbackMode): number {
  const sortKey = anchor.sort_key ?? 0
  if (mode === 'before') {
    const prev = messages.filter((m) => (m.sort_key ?? 0) < sortKey)
    if (!prev.length) return -1
    return Math.max(...prev.map((m) => m.sort_key ?? 0))
  }
  const replySk = assistantReplySortKey(anchor, messages)
  if (replySk != null) return replySk
  return sortKey
}

export function hasRollbackTrailing(anchor: ChatMessage, messages: ChatMessage[], mode: RollbackMode): boolean {
  const cutoff = rollbackCutoffSortKey(anchor, messages, mode)
  return messages.some((m) => (m.sort_key ?? 0) > cutoff)
}
