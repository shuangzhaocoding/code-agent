import type { ChatMessage, Block } from '@/protocol/applyEvent'

function blockPlainText(block: Block): string {
  if (block.type === 'user.text' || block.type === 'assistant.markdown') {
    return (block.text || '').trim()
  }
  if (block.type === 'assistant.thinking') {
    const t = (block.text || '').trim()
    return t ? `[thinking]\n${t}` : ''
  }
  if (block.type === 'todo') {
    const t = (block.text || '').trim()
    return t ? `[todo]\n${t}` : '[todo]'
  }
  if (block.type === 'tool' || block.type.startsWith('tool.')) {
    const name = String(block.meta?.tool || block.meta?.name || 'tool')
    const summary = String(block.meta?.summary || block.text || '').trim()
    return summary ? `[tool:${name}] ${summary}` : `[tool:${name}]`
  }
  if (block.type === 'error') {
    return `[error] ${(block.text || '').trim()}`
  }
  if (block.type === 'file.diff' || block.type === 'file.write' || block.type.startsWith('file.')) {
    const path = String(block.meta?.path || '')
    return path ? `[file] ${path}` : '[file]'
  }
  return ''
}

export function messagePlainText(msg: ChatMessage): string {
  return msg.blocks
    .map(blockPlainText)
    .filter(Boolean)
    .join('\n')
    .trim()
}

export function conversationToMarkdown(opts: {
  title: string
  id: string
  messages: ChatMessage[]
  exportedAt?: string
}): string {
  const when = opts.exportedAt || new Date().toISOString()
  const lines: string[] = [
    `# ${opts.title || 'Conversation'}`,
    '',
    `- id: \`${opts.id}\``,
    `- exported: ${when}`,
    '',
  ]
  for (const msg of opts.messages) {
    const role = msg.role === 'user' ? 'User' : msg.role === 'assistant' ? 'Assistant' : msg.role
    const body = messagePlainText(msg)
    lines.push(`## ${role}`)
    lines.push('')
    lines.push(body || '_empty_')
    lines.push('')
  }
  return lines.join('\n')
}

export function conversationToJson(opts: {
  title: string
  id: string
  messages: ChatMessage[]
  exportedAt?: string
}): string {
  return JSON.stringify(
    {
      id: opts.id,
      title: opts.title,
      exported_at: opts.exportedAt || new Date().toISOString(),
      messages: opts.messages,
    },
    null,
    2,
  )
}

export function downloadTextFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function safeFilename(name: string): string {
  return (name || 'conversation').replace(/[\\/:*?"<>|]+/g, '_').slice(0, 80)
}
