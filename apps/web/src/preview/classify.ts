export type OpenFileKind =
  | 'text'
  | 'image'
  | 'video'
  | 'html'
  | 'pdf'
  | 'docx'
  | 'xlsx'
  | 'pptx'
  | 'binary'

const IMAGE_EXT = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'ico'])
const VIDEO_EXT = new Set(['mp4', 'webm', 'ogg', 'mov', 'm4v'])
const HTML_EXT = new Set(['html', 'htm'])
const PDF_EXT = new Set(['pdf'])
const DOCX_EXT = new Set(['docx'])
const XLSX_EXT = new Set(['xlsx', 'xls'])
const PPTX_EXT = new Set(['pptx'])

/** Known text-ish extensions that should stay in Monaco even if binary sniffing would fail later. */
const TEXT_EXT = new Set([
  'ts',
  'tsx',
  'js',
  'jsx',
  'mjs',
  'cjs',
  'vue',
  'py',
  'pyi',
  'md',
  'mdx',
  'markdown',
  'json',
  'jsonc',
  'css',
  'scss',
  'less',
  'sass',
  'html',
  'htm',
  'yaml',
  'yml',
  'toml',
  'ini',
  'cfg',
  'conf',
  'txt',
  'log',
  'csv',
  'tsv',
  'xml',
  'svg',
  'sh',
  'bash',
  'zsh',
  'fish',
  'rs',
  'go',
  'java',
  'kt',
  'c',
  'h',
  'cpp',
  'hpp',
  'cc',
  'cs',
  'rb',
  'php',
  'sql',
  'graphql',
  'gql',
  'env',
  'gitignore',
  'dockerignore',
  'editorconfig',
  'dockerfile',
  'makefile',
  'r',
  'swift',
  'dart',
  'lua',
  'proto',
  'tf',
  'hcl',
])

export function extOf(path: string): string {
  const base = path.split('/').pop() || path
  const i = base.lastIndexOf('.')
  if (i <= 0) return ''
  return base.slice(i + 1).toLowerCase()
}

export function classifyOpenKind(path: string): OpenFileKind {
  const ext = extOf(path)
  if (IMAGE_EXT.has(ext)) return 'image'
  if (VIDEO_EXT.has(ext)) return 'video'
  if (HTML_EXT.has(ext)) return 'html'
  if (PDF_EXT.has(ext)) return 'pdf'
  if (DOCX_EXT.has(ext)) return 'docx'
  if (XLSX_EXT.has(ext)) return 'xlsx'
  if (PPTX_EXT.has(ext)) return 'pptx'
  if (!ext || TEXT_EXT.has(ext)) return 'text'
  // Unknown extension: try text first via API; binary falls back in openPath on file.binary
  return 'text'
}

export function isPreviewKind(kind: OpenFileKind): boolean {
  return kind !== 'text'
}

/** Kinds that can be edited in Monaco (including dual preview/source). */
export function isEditableKind(kind: OpenFileKind): boolean {
  return kind === 'text' || kind === 'html'
}

export function rawFileUrl(workspaceId: string, path: string): string {
  return `/api/workspaces/${workspaceId}/file/raw?path=${encodeURIComponent(path)}`
}
