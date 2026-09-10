/** Format editor text for common languages. Returns null if unsupported / failed. */

const PRETTIER_EXTS = new Set([
  'js', 'jsx', 'mjs', 'cjs',
  'ts', 'tsx', 'mts', 'cts',
  'json', 'jsonc',
  'css', 'scss', 'less',
  'html', 'htm', 'vue',
  'md', 'markdown', 'mdx',
  'yml', 'yaml',
])

function extOf(path: string) {
  const base = path.split('/').pop() || path
  const i = base.lastIndexOf('.')
  return i > 0 ? base.slice(i + 1).toLowerCase() : ''
}

function prettierParser(ext: string): string | null {
  if (['js', 'jsx', 'mjs', 'cjs'].includes(ext)) return 'babel'
  if (['ts', 'tsx', 'mts', 'cts'].includes(ext)) return 'typescript'
  if (ext === 'json' || ext === 'jsonc') return 'json'
  if (ext === 'css') return 'css'
  if (ext === 'scss') return 'scss'
  if (ext === 'less') return 'less'
  if (ext === 'html' || ext === 'htm' || ext === 'vue') return 'html'
  if (ext === 'md' || ext === 'markdown' || ext === 'mdx') return 'markdown'
  if (ext === 'yml' || ext === 'yaml') return 'yaml'
  return null
}

export function canFormatPath(path: string) {
  return PRETTIER_EXTS.has(extOf(path))
}

export async function formatDocumentText(path: string, content: string): Promise<string | null> {
  const ext = extOf(path)
  if (ext === 'json' || ext === 'jsonc') {
    try {
      const parsed = JSON.parse(content)
      return `${JSON.stringify(parsed, null, 2)}\n`
    } catch {
      /* fall through to prettier for jsonc comments etc. */
    }
  }
  const parser = prettierParser(ext)
  if (!parser) return null
  try {
    const prettier = await import('prettier/standalone')
    const plugins = await Promise.all([
      import('prettier/plugins/babel'),
      import('prettier/plugins/estree'),
      import('prettier/plugins/typescript'),
      import('prettier/plugins/postcss'),
      import('prettier/plugins/html'),
      import('prettier/plugins/markdown'),
      import('prettier/plugins/yaml'),
    ])
    const formatted = await prettier.format(content, {
      parser,
      plugins: plugins.map((p) => p.default ?? p),
      printWidth: 100,
      singleQuote: true,
      trailingComma: 'all',
      semi: false,
    })
    return formatted
  } catch {
    return null
  }
}
