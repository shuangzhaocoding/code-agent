/** Monaco editor color theme preference (independent of app light/dark). */

export type MonacoThemeData = {
  base: 'vs' | 'vs-dark' | 'hc-black' | 'hc-light'
  inherit: boolean
  rules: Array<{
    token: string
    foreground?: string
    background?: string
    fontStyle?: string
  }>
  colors: Record<string, string>
}

export type EditorThemeOption = {
  id: string
  label: string
  group: 'auto' | 'builtin' | 'community'
}

export const EDITOR_THEME_AUTO = 'ca-auto'
export const EDITOR_THEME_EVENT = 'ca-editor-theme'
const STORAGE_KEY = 'ca.editorTheme'

/** Built-in Monaco themes (no JSON load). */
export const BUILTIN_EDITOR_THEMES: EditorThemeOption[] = [
  { id: 'vs', label: 'Light (vs)', group: 'builtin' },
  { id: 'vs-dark', label: 'Dark (vs-dark)', group: 'builtin' },
  { id: 'hc-black', label: 'High Contrast Dark', group: 'builtin' },
  { id: 'hc-light', label: 'High Contrast Light', group: 'builtin' },
]

/**
 * monaco-themes themelist: id → JSON file basename (without .json).
 * Dominion Day ships in the package but is missing from themelist.
 */
const MONACO_THEME_FILES: Record<string, string> = {
  active4d: 'Active4D',
  'all-hallows-eve': 'All Hallows Eve',
  amy: 'Amy',
  'birds-of-paradise': 'Birds of Paradise',
  blackboard: 'Blackboard',
  'brilliance-black': 'Brilliance Black',
  'brilliance-dull': 'Brilliance Dull',
  'chrome-devtools': 'Chrome DevTools',
  'clouds-midnight': 'Clouds Midnight',
  clouds: 'Clouds',
  cobalt: 'Cobalt',
  cobalt2: 'Cobalt2',
  dawn: 'Dawn',
  'dominion-day': 'Dominion Day',
  dracula: 'Dracula',
  dreamweaver: 'Dreamweaver',
  eiffel: 'Eiffel',
  'espresso-libre': 'Espresso Libre',
  'github-dark': 'GitHub Dark',
  'github-light': 'GitHub Light',
  github: 'GitHub',
  idle: 'IDLE',
  iplastic: 'iPlastic',
  idlefingers: 'idleFingers',
  katzenmilch: 'Katzenmilch',
  krtheme: 'krTheme',
  'kuroir-theme': 'Kuroir Theme',
  lazy: 'LAZY',
  'magicwb--amiga-': 'MagicWB (Amiga)',
  merbivore: 'Merbivore',
  'merbivore-soft': 'Merbivore Soft',
  monoindustrial: 'monoindustrial',
  monokai: 'Monokai',
  'monokai-bright': 'Monokai Bright',
  'night-owl': 'Night Owl',
  nord: 'Nord',
  'oceanic-next': 'Oceanic Next',
  'pastels-on-dark': 'Pastels on Dark',
  'slush-and-poppies': 'Slush and Poppies',
  'solarized-dark': 'Solarized-dark',
  'solarized-light': 'Solarized-light',
  spacecadet: 'SpaceCadet',
  sunburst: 'Sunburst',
  'textmate--mac-classic-': 'Textmate (Mac Classic)',
  tomorrow: 'Tomorrow',
  'tomorrow-night': 'Tomorrow-Night',
  'tomorrow-night-blue': 'Tomorrow-Night-Blue',
  'tomorrow-night-bright': 'Tomorrow-Night-Bright',
  'tomorrow-night-eighties': 'Tomorrow-Night-Eighties',
  twilight: 'Twilight',
  'upstream-sunburst': 'Upstream Sunburst',
  'vibrant-ink': 'Vibrant Ink',
  'xcode-default': 'Xcode_default',
  zenburnesque: 'Zenburnesque',
}

const DISPLAY_LABELS: Record<string, string> = {
  active4d: 'Active4D',
  'all-hallows-eve': 'All Hallows Eve',
  amy: 'Amy',
  'birds-of-paradise': 'Birds of Paradise',
  blackboard: 'Blackboard',
  'brilliance-black': 'Brilliance Black',
  'brilliance-dull': 'Brilliance Dull',
  'chrome-devtools': 'Chrome DevTools',
  'clouds-midnight': 'Clouds Midnight',
  clouds: 'Clouds',
  cobalt: 'Cobalt',
  cobalt2: 'Cobalt2',
  dawn: 'Dawn',
  'dominion-day': 'Dominion Day',
  dracula: 'Dracula',
  dreamweaver: 'Dreamweaver',
  eiffel: 'Eiffel',
  'espresso-libre': 'Espresso Libre',
  'github-dark': 'GitHub Dark',
  'github-light': 'GitHub Light',
  github: 'GitHub',
  idle: 'IDLE',
  iplastic: 'iPlastic',
  idlefingers: 'idleFingers',
  katzenmilch: 'Katzenmilch',
  krtheme: 'krTheme',
  'kuroir-theme': 'Kuroir Theme',
  lazy: 'LAZY',
  'magicwb--amiga-': 'MagicWB (Amiga)',
  merbivore: 'Merbivore',
  'merbivore-soft': 'Merbivore Soft',
  monoindustrial: 'monoindustrial',
  monokai: 'Monokai',
  'monokai-bright': 'Monokai Bright',
  'night-owl': 'Night Owl',
  nord: 'Nord',
  'oceanic-next': 'Oceanic Next',
  'pastels-on-dark': 'Pastels on Dark',
  'slush-and-poppies': 'Slush and Poppies',
  'solarized-dark': 'Solarized Dark',
  'solarized-light': 'Solarized Light',
  spacecadet: 'SpaceCadet',
  sunburst: 'Sunburst',
  'textmate--mac-classic-': 'Textmate (Mac Classic)',
  tomorrow: 'Tomorrow',
  'tomorrow-night': 'Tomorrow Night',
  'tomorrow-night-blue': 'Tomorrow Night Blue',
  'tomorrow-night-bright': 'Tomorrow Night Bright',
  'tomorrow-night-eighties': 'Tomorrow Night Eighties',
  twilight: 'Twilight',
  'upstream-sunburst': 'Upstream Sunburst',
  'vibrant-ink': 'Vibrant Ink',
  'xcode-default': 'Xcode Default',
  zenburnesque: 'Zenburnesque',
}

/** Vite-bundled loaders keyed by absolute-ish path ending in `FileName.json`. */
const themeJsonLoaders = import.meta.glob('../../node_modules/monaco-themes/themes/*.json') as Record<
  string,
  () => Promise<{ default: MonacoThemeData } | MonacoThemeData>
>

const loadersByFile = new Map<string, () => Promise<MonacoThemeData>>()
for (const [path, loader] of Object.entries(themeJsonLoaders)) {
  const file = path.split('/').pop()?.replace(/\.json$/i, '')
  if (!file || file === 'themelist') continue
  loadersByFile.set(file, async () => {
    const mod = await loader()
    return (mod as { default?: MonacoThemeData }).default ?? (mod as MonacoThemeData)
  })
}

const registered = new Set<string>(['vs', 'vs-dark', 'hc-black', 'hc-light'])

function isKnownId(id: string): boolean {
  if (id === EDITOR_THEME_AUTO) return true
  if (BUILTIN_EDITOR_THEMES.some((t) => t.id === id)) return true
  return id in MONACO_THEME_FILES
}

export function listEditorThemeOptions(autoLabel: string): EditorThemeOption[] {
  const community = Object.keys(MONACO_THEME_FILES)
    .sort((a, b) => (DISPLAY_LABELS[a] || a).localeCompare(DISPLAY_LABELS[b] || b, undefined, { sensitivity: 'base' }))
    .map((id) => ({
      id,
      label: DISPLAY_LABELS[id] || id,
      group: 'community' as const,
    }))
  return [
    { id: EDITOR_THEME_AUTO, label: autoLabel, group: 'auto' },
    ...BUILTIN_EDITOR_THEMES,
    ...community,
  ]
}

export function getEditorThemeId(): string {
  if (typeof localStorage === 'undefined') return EDITOR_THEME_AUTO
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved && isKnownId(saved)) return saved
  return EDITOR_THEME_AUTO
}

export function setEditorThemeId(id: string): string {
  const next = isKnownId(id) ? id : EDITOR_THEME_AUTO
  localStorage.setItem(STORAGE_KEY, next)
  window.dispatchEvent(new CustomEvent(EDITOR_THEME_EVENT, { detail: next }))
  return next
}

async function ensureCommunityTheme(
  monaco: { editor: { defineTheme: (name: string, data: MonacoThemeData) => void } },
  id: string,
): Promise<boolean> {
  if (registered.has(id)) return true
  const file = MONACO_THEME_FILES[id]
  if (!file) return false
  const loader = loadersByFile.get(file)
  if (!loader) return false
  const data = await loader()
  // Monaco types are stricter; community JSON matches IStandaloneThemeData at runtime.
  monaco.editor.defineTheme(id, data)
  registered.add(id)
  return true
}

type MonacoLike = {
  editor: {
    defineTheme: (name: string, data: MonacoThemeData) => void
    setTheme: (name: string) => void
  }
}

/**
 * Apply the user's chosen editor theme.
 * For `ca-auto`, `defineAutoTheme` must define and set `ca-editor`.
 */
export async function applyMonacoEditorTheme(
  monaco: MonacoLike,
  defineAutoTheme: () => void,
): Promise<string> {
  const id = getEditorThemeId()
  if (id === EDITOR_THEME_AUTO) {
    defineAutoTheme()
    return EDITOR_THEME_AUTO
  }
  if (BUILTIN_EDITOR_THEMES.some((t) => t.id === id)) {
    monaco.editor.setTheme(id)
    return id
  }
  const ok = await ensureCommunityTheme(monaco, id)
  if (!ok) {
    defineAutoTheme()
    return EDITOR_THEME_AUTO
  }
  monaco.editor.setTheme(id)
  return id
}

export function monacoThemeNameForCreate(): string {
  const id = getEditorThemeId()
  if (id === EDITOR_THEME_AUTO) return 'ca-editor'
  return id
}
