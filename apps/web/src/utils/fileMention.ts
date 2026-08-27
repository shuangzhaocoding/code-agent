export type FileMentionItem = {
  name: string
  path: string
  is_dir: boolean
  lineStart?: number
  lineEnd?: number
}

export function fileNameFromPath(path: string) {
  return path.split('/').filter(Boolean).pop() || path
}

export function mentionToken(item: FileMentionItem) {
  if (!item.is_dir && item.lineStart && item.lineEnd) {
    if (item.lineStart === item.lineEnd) return `@${item.path}:${item.lineStart}`
    return `@${item.path}:${item.lineStart}-${item.lineEnd}`
  }
  return `@${item.path}`
}

export type PasteSegment =
  | { type: 'text'; text: string }
  | { type: 'mention'; item: FileMentionItem }

const MENTION_INLINE_RE = /@([^\s@]+)(?::(\d+)(?:-(\d+))?)?/g

export function parseMentionSegments(text: string, resolveIsDir?: (path: string) => boolean): PasteSegment[] {
  const segments: PasteSegment[] = []
  let last = 0
  let match: RegExpExecArray | null
  const re = new RegExp(MENTION_INLINE_RE.source, 'g')
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      segments.push({ type: 'text', text: text.slice(last, match.index) })
    }
    const path = match[1]
    const lineStart = match[2] ? Number(match[2]) : undefined
    const lineEnd = match[3] ? Number(match[3]) : lineStart
    segments.push({
      type: 'mention',
      item: {
        path,
        name: fileNameFromPath(path),
        is_dir: resolveIsDir?.(path) ?? false,
        lineStart,
        lineEnd,
      },
    })
    last = match.index + match[0].length
  }
  if (last < text.length) segments.push({ type: 'text', text: text.slice(last) })
  return segments
}

export function hasInlineMentions(text: string) {
  return MENTION_INLINE_RE.test(text)
}

export function normalizeClipboardText(text: string) {
  return text.replace(/\r\n/g, '\n')
}

type InlinePart = { kind: 'text'; value: string } | { kind: 'mention'; value: string }

export function isMentionOnlyParagraph(parts: InlinePart[]): boolean {
  if (!parts.length) return false
  return parts.every((p) => p.kind === 'mention' || (p.kind === 'text' && !p.value.trim()))
}

function paragraphHasMention(parts: InlinePart[]) {
  return parts.some((p) => p.kind === 'mention')
}

/** Merge atom-split mention paragraphs with adjacent inline content. */
function shouldMergeParagraphs(buffer: InlinePart[], parts: InlinePart[]): boolean {
  if (!buffer.length) return false
  if (isMentionOnlyParagraph(buffer) || isMentionOnlyParagraph(parts)) return true
  return paragraphHasMention(buffer) || paragraphHasMention(parts)
}

/** Serialize paragraph parts; merge mention-only blocks with following text (inline flow). */
export function serializeParagraphs(partsByParagraph: InlinePart[][]): string {
  const lines: string[] = []
  let buffer: InlinePart[] = []

  const flush = () => {
    if (buffer.length) {
      lines.push(joinInlineParts(buffer))
      buffer = []
    }
  }

  for (const parts of partsByParagraph) {
    if (!parts.length) {
      // TipTap atom nodes often insert spurious empty paragraphs — skip while buffering.
      if (buffer.length) continue
      lines.push('')
      continue
    }

    if (shouldMergeParagraphs(buffer, parts)) {
      buffer.push(...parts)
      continue
    }

    flush()
    buffer = parts
  }
  flush()

  return lines.join('\n')
}

/** Join mention tokens and surrounding text with readable spacing. */
export function joinInlineParts(parts: InlinePart[]): string {
  let out = ''
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i]
    if (part.kind === 'text') {
      out += part.value
      continue
    }
    if (out && !/\s$/.test(out)) out += ' '
    out += part.value
    const next = parts[i + 1]
    if (next?.kind === 'text' && next.value && !/^[\s\n]/.test(next.value)) {
      out += ' '
    }
  }
  return out
}

export function segmentsToInlineNodes(segments: PasteSegment[]) {
  const nodes: Array<{
    type: string
    text?: string
    attrs?: {
      path: string
      name: string
      isDir: boolean
      lineStart: number | null
      lineEnd: number | null
    }
  }> = []
  for (const seg of segments) {
    if (seg.type === 'text') {
      if (seg.text) nodes.push({ type: 'text', text: seg.text })
    } else {
      nodes.push({
        type: 'fileMention',
        attrs: {
          path: seg.item.path,
          name: seg.item.name,
          isDir: seg.item.is_dir,
          lineStart: seg.item.lineStart ?? null,
          lineEnd: seg.item.lineEnd ?? null,
        },
      })
    }
  }
  return nodes
}

export function messageTextToEditorDoc(text: string, resolveIsDir?: (path: string) => boolean) {
  const rawLines = normalizeClipboardText(text).split('\n')
  const mergedLines: string[] = []

  for (const line of rawLines) {
    if (!line) {
      mergedLines.push('')
      continue
    }
    const prev = mergedLines[mergedLines.length - 1]
    if (prev && hasInlineMentions(prev) && !hasInlineMentions(line)) {
      const prevParts = parseMentionSegments(prev, resolveIsDir)
      if (prevParts.every((s) => s.type === 'mention' || (s.type === 'text' && !s.text.trim()))) {
        mergedLines[mergedLines.length - 1] = `${prev} ${line}`
        continue
      }
    }
    mergedLines.push(line)
  }

  return {
    type: 'doc',
    content: mergedLines.map((line) => ({
      type: 'paragraph',
      content: line ? segmentsToInlineNodes(parseMentionSegments(line, resolveIsDir)) : [],
    })),
  }
}

export function messageHasInlineMentions(text: string) {
  return hasInlineMentions(text)
}
