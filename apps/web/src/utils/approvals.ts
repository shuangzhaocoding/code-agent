import type { Block, ChatMessage } from '@/protocol/applyEvent'

export type PendingApproval = {
  approvalId: string
  blockId: string
  tool: string
  summary: string
  details: string
  kind: string
}

export function isPendingApprovalBlock(block: Block): boolean {
  if (block.type !== 'approval') return false
  if (String(block.meta.decision || '')) return false
  return block.status === 'streaming'
}

export function formatApprovalDetails(raw: unknown): string {
  if (raw == null || raw === '') return ''
  if (typeof raw === 'string') return raw
  try {
    return JSON.stringify(raw, null, 2)
  } catch {
    return String(raw)
  }
}

export function pendingApprovalsFromMessages(messages: ChatMessage[]): PendingApproval[] {
  const out: PendingApproval[] = []
  for (const msg of messages) {
    if (msg.role !== 'assistant') continue
    for (const block of msg.blocks) {
      if (!isPendingApprovalBlock(block)) continue
      const approvalId = String(block.meta.approval_id || '')
      if (!approvalId) continue
      out.push({
        approvalId,
        blockId: block.id,
        tool: String(block.meta.tool || 'tool'),
        summary: String(block.meta.summary || '需要确认这次操作'),
        details: formatApprovalDetails(block.meta.details),
        kind: String(block.meta.kind || 'danger'),
      })
    }
  }
  return out
}

/** Attach a pending approval hint to the matching in-flight tool.call. */
export function matchApprovalHint(
  toolBlock: Block,
  blocks: Block[],
  usedApprovalIds: Set<string>,
): Block | undefined {
  if (toolBlock.type !== 'tool.call') return undefined
  const toolName = String(toolBlock.meta.name || '')
  const idx = blocks.indexOf(toolBlock)

  const tryMatch = (block: Block) => {
    if (!isPendingApprovalBlock(block) || usedApprovalIds.has(block.id)) return false
    const name = String(block.meta.tool || '')
    return !name || name === toolName
  }

  if (idx >= 0) {
    for (let i = idx + 1; i < blocks.length; i++) {
      const block = blocks[i]
      if (block.type === 'tool.call') break
      if (tryMatch(block)) {
        usedApprovalIds.add(block.id)
        return block
      }
    }
  }
  for (const block of blocks) {
    if (tryMatch(block)) {
      usedApprovalIds.add(block.id)
      return block
    }
  }
  return undefined
}
