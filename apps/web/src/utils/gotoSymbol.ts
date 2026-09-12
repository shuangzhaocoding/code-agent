const DEF_SOURCES = [
  String.raw`^\s*(export\s+)?(default\s+)?(async\s+)?function\s*\*?\s+NAME\b`,
  String.raw`^\s*(export\s+)?(default\s+)?class\s+NAME\b`,
  String.raw`^\s*(async\s+)?def\s+NAME\s*\(`,
  String.raw`^\s*(pub(\s*\([^)]+\))?\s+)?(async\s+)?fn\s+NAME\b`,
  String.raw`^\s*(export\s+)?(type|interface|enum|struct|trait|impl)\s+NAME\b`,
  String.raw`^\s*(func|function)\s+NAME\s*\(`,
  String.raw`^\s*(export\s+)?(const|let|var)\s+NAME\b`,
  String.raw`^\s*NAME\s*=\s*(async\s+)?(function\b|\(|class\b)`,
]

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function isDefinitionLine(symbol: string, line: string) {
  const name = symbol.trim()
  if (!name) return false
  const escaped = escapeRegExp(name)
  return DEF_SOURCES.some((src) => new RegExp(src.replace('NAME', escaped)).test(line))
}

export function identifierAt(
  model: { getWordAtPosition: (pos: { lineNumber: number; column: number }) => { word: string; startColumn: number; endColumn: number } | null },
  position: { lineNumber: number; column: number },
) {
  const word = model.getWordAtPosition(position)
  if (!word?.word || /^\d+$/.test(word.word)) return null
  return {
    word: word.word,
    startColumn: word.startColumn,
    endColumn: word.endColumn,
  }
}

export function findLocalDefinitions(
  model: { getLineCount: () => number; getLineContent: (line: number) => string },
  symbol: string,
) {
  const hits: { line: number; text: string }[] = []
  const n = model.getLineCount()
  for (let i = 1; i <= n; i++) {
    const text = model.getLineContent(i)
    if (isDefinitionLine(symbol, text)) hits.push({ line: i, text: text.trim().slice(0, 240) })
  }
  return hits
}

/** Expand empty selection to the current line, or an indented block if it looks like a definition. */
export function expandInlineRange(
  model: { getLineCount: () => number; getLineContent: (line: number) => string; getLineMaxColumn: (line: number) => number },
  position: { lineNumber: number; column: number },
) {
  const startLine = Math.max(1, position.lineNumber)
  const line = model.getLineContent(startLine)
  const indent = (line.match(/^\s*/) || [''])[0].length
  const trimmed = line.trim()
  const looksDef =
    /^(export\s+|default\s+|async\s+|public\s+|private\s+|protected\s+|static\s+)*(def|function|class|fn|func|interface|type|enum|struct)\b/.test(
      trimmed,
    ) || isDefinitionLine(trimmed.split(/[\s(<{]/)[0] || '', line)
  let endLine = startLine
  if (looksDef) {
    const total = model.getLineCount()
    for (let i = startLine + 1; i <= total; i++) {
      const next = model.getLineContent(i)
      if (!next.trim()) {
        endLine = i
        continue
      }
      const nextIndent = (next.match(/^\s*/) || [''])[0].length
      if (nextIndent <= indent) break
      endLine = i
    }
  }
  return {
    startLineNumber: startLine,
    startColumn: 1,
    endLineNumber: endLine,
    endColumn: model.getLineMaxColumn(endLine),
  }
}
