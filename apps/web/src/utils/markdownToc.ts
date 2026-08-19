export interface MarkdownTocItem {
  id: string
  text: string
  level: number
}

export function slugifyHeading(text: string): string {
  const slug = String(text)
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^\w\u4e00-\u9fff-]+/g, '')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
  return slug || 'heading'
}

function plainHeadingText(raw: string): string {
  return raw
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/(\*\*|__)(.*?)\1/g, '$2')
    .replace(/(\*|_)(.*?)\1/g, '$2')
    .replace(/~~(.*?)~~/g, '$1')
    .replace(/\\([\\`*_{}[\]()#+\-.!])/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

export function extractMarkdownToc(source: string): MarkdownTocItem[] {
  const items: MarkdownTocItem[] = []
  const seen = new Map<string, number>()
  let inFence = false

  for (const line of String(source || '').split(/\r?\n/)) {
    const trimmed = line.trim()
    if (trimmed.startsWith('```') || trimmed.startsWith('~~~')) {
      inFence = !inFence
      continue
    }
    if (inFence) continue

    const match = /^(#{1,6})\s+(.+?)\s*$/.exec(line)
    if (!match) continue

    const level = match[1].length
    const text = plainHeadingText(match[2].replace(/\s+#+\s*$/, ''))
    if (!text) continue

    let id = slugifyHeading(text)
    const count = seen.get(id) ?? 0
    seen.set(id, count + 1)
    if (count > 0) id = `${id}-${count}`
    items.push({ id, text, level })
  }

  return items
}
