import type { StreamEnvelope } from '@/api/http'

export type Block = {
  id: string
  type: string
  text: string
  meta: Record<string, unknown>
  status: string
  started_at?: number | string
  ended_at?: number | string
}

export type ChatMessage = {
  id: string
  role: string
  blocks: Block[]
  run_id?: string | null
  sort_key?: number
  created_at?: string | null
  ended_at?: string | null
}

function findAssistantIndex(messages: ChatMessage[], runId: string): number {
  return messages.findIndex((m) => m.role === 'assistant' && (m.run_id === runId || m.id === `run-${runId}`))
}

export function applyEvent(messages: ChatMessage[], event: StreamEnvelope): ChatMessage[] {
  const payload = event.payload || {}
  if (event.type === 'block.started') {
    const idx = findAssistantIndex(messages, event.run_id)
    if (idx >= 0) {
      const target = messages[idx]
      if (target.blocks.some((b) => b.id === payload.block_id)) return messages
      const next = messages.slice()
      next[idx] = {
        ...target,
        blocks: [
          ...target.blocks,
          {
            id: String(payload.block_id),
            type: String(payload.block_type || 'assistant.markdown'),
            text: '',
            meta: (payload.meta as Record<string, unknown>) || {},
            status: 'streaming',
            started_at: Date.now(),
          },
        ],
      }
      return next
    }
    return [
      ...messages,
      {
        id: `run-${event.run_id}`,
        role: 'assistant',
        run_id: event.run_id,
        blocks: [
          {
            id: String(payload.block_id),
            type: String(payload.block_type || 'assistant.markdown'),
            text: '',
            meta: (payload.meta as Record<string, unknown>) || {},
            status: 'streaming',
            started_at: Date.now(),
          },
        ],
        created_at: new Date().toISOString(),
      },
    ]
  }
  if (event.type === 'block.delta' || event.type === 'block.completed') {
    const idx = findAssistantIndex(messages, event.run_id)
    if (idx < 0) return messages
    const target = messages[idx]
    let touched = false
    const blocks = target.blocks.map((b) => {
      if (b.id !== payload.block_id) return b
      touched = true
      const copy = { ...b, meta: { ...b.meta } }
      if (event.type === 'block.delta') {
        if (b.status && b.status !== 'streaming') return b
        copy.text += String(payload.text || '')
        if (payload.meta) Object.assign(copy.meta, payload.meta)
      } else {
        copy.status = String(payload.status || 'ok')
        copy.ended_at = Date.now()
        if (payload.meta) Object.assign(copy.meta, payload.meta)
      }
      return copy
    })
    if (!touched) return messages
    const next = messages.slice()
    next[idx] = { ...target, blocks }
    return next
  }
  return messages
}
