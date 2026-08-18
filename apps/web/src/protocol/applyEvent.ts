import type { StreamEnvelope } from '@/api/http'

export type Block = {
  id: string
  type: string
  text: string
  meta: Record<string, unknown>
  status: string
}

export type ChatMessage = {
  id: string
  role: string
  blocks: Block[]
  run_id?: string | null
}

export function applyEvent(messages: ChatMessage[], event: StreamEnvelope): ChatMessage[] {
  const payload = event.payload || {}
  if (event.type === 'block.started') {
    const next = messages.map((m) => ({ ...m, blocks: m.blocks.map((b) => ({ ...b })) }))
    let assistant = [...next].reverse().find((m) => m.role === 'assistant' && m.run_id === event.run_id)
    if (!assistant) {
      assistant = {
        id: `run-${event.run_id}`,
        role: 'assistant',
        run_id: event.run_id,
        blocks: [],
      }
      next.push(assistant)
    }
    if (!assistant.blocks.some((b) => b.id === payload.block_id)) {
      assistant.blocks.push({
        id: String(payload.block_id),
        type: String(payload.block_type || 'assistant.markdown'),
        text: '',
        meta: (payload.meta as Record<string, unknown>) || {},
        status: 'streaming',
      })
    }
    return next
  }
  if (event.type === 'block.delta' || event.type === 'block.completed') {
    return messages.map((m) => {
      if (m.run_id !== event.run_id && m.id !== `run-${event.run_id}`) return m
      return {
        ...m,
        blocks: m.blocks.map((b) => {
          if (b.id !== payload.block_id) return b
          const copy = { ...b, meta: { ...b.meta } }
          if (event.type === 'block.delta') {
            copy.text += String(payload.text || '')
            if (payload.meta) Object.assign(copy.meta, payload.meta)
          } else {
            copy.status = String(payload.status || 'ok')
            if (payload.meta) Object.assign(copy.meta, payload.meta)
          }
          return copy
        }),
      }
    })
  }
  return messages
}
