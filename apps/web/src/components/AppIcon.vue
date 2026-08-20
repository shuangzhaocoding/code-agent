<script setup lang="ts">
export type AppIconName =
  | 'home'
  | 'dashboard'
  | 'user'
  | 'users'
  | 'shield'
  | 'key'
  | 'sun'
  | 'moon'
  | 'plus'
  | 'logout'
  | 'inbox'
  | 'menu'
  | 'close'
  | 'folder'
  | 'file'
  | 'more'
  | 'save'
  | 'arrow-left'
  | 'chevron-right'
  | 'chevron'
  | 'globe'
  | 'check'
  | 'dot'
  | 'chat'
  | 'settings'
  | 'sliders'
  | 'play'
  | 'eye'
  | 'refresh'
  | 'copy'
  | 'close-others'
  | 'close-left'
  | 'close-right'
  | 'close-all'
  | 'close-saved'
  | 'rocket'
  | 'clock'
  | 'download'
  | 'panel-left'
  | 'panel-right'
  | 'panel-bottom'
  | 'terminal'
  | 'wrench'
  | 'trash'
  | 'pencil'
  | 'atom'
  | 'sparkles'
  | 'upload'
  | 'book'
  | 'puzzle'
  | 'chip'
  | 'git'
  | 'search'
  | 'file-plus'
  | 'folder-plus'
  | 'file-edit'
  | 'alert'
  | 'think'
  | 'gear'
  | 'spark'
  | 'zap'
  | 'layout-left'
  | 'layout-right'
  | 'layout-bottom'
  | 'edit'

const props = withDefaults(
  defineProps<{
    name: AppIconName | string
    size?: number | string
  }>(),
  { size: 18 },
)

const aliases: Record<string, keyof typeof paths> = {
  gear: 'sliders',
  spark: 'sparkles',
  edit: 'pencil',
  atom: 'sparkles',
  settings: 'sliders',
  'layout-left': 'panel-left',
  'layout-right': 'panel-right',
  'layout-bottom': 'panel-bottom',
}

const paths: Record<string, string[]> = {
  home: ['M5 10.5 12 4.5 19 10.5V19a1.5 1.5 0 0 1-1.5 1.5H15v-5.5H9V20.5H6.5A1.5 1.5 0 0 1 5 19v-8.5Z'],
  dashboard: ['M4 4.5h7v7h-7v-7Z', 'M13 4.5h7v4h-7v-4Z', 'M13 10.5h7v9h-7v-9Z', 'M4 13.5h7v6h-7v-6Z'],
  user: ['M12 11.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z', 'M5.5 19.5a6.5 6.5 0 0 1 13 0'],
  users: ['M9.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M3.5 19.5a6 6 0 0 1 12 0', 'M16.5 11a2.5 2.5 0 1 0 0-5', 'M19.5 19.5a4.5 4.5 0 0 0-3-4.2'],
  shield: ['M12 3.5 5.5 6.5v5.5c0 4 2.8 6.8 6.5 8.5 3.7-1.7 6.5-4.5 6.5-8.5V6.5L12 3.5Z'],
  key: ['M8.5 14a3.5 3.5 0 1 1 3.2-5.2L20.5 17.5 18 20l-2.5-2.5-1.5 1.5', 'M8.5 10h.01'],
  sun: ['M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Z', 'M12 2.5v2', 'M12 19.5v2', 'M4.5 4.5l1.4 1.4', 'M18.1 18.1l1.4 1.4', 'M2.5 12h2', 'M19.5 12h2', 'M4.5 19.5l1.4-1.4', 'M18.1 5.9l1.4-1.4'],
  moon: ['M18 14.5A7 7 0 0 1 9.5 5 7 7 0 1 0 18 14.5Z'],
  plus: ['M12 5.5v13', 'M5.5 12h13'],
  logout: ['M10 7.5V6a1 1 0 0 1 1-1h7.5a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H11a1 1 0 0 1-1-1v-1.5', 'M4.5 12H14', 'M11.5 8.5 15 12l-3.5 3.5'],
  inbox: ['M4 6.5h16v11H4v-11Z', 'M4 11h4.5L10 14h4l1.5-3H20'],
  menu: ['M5 7.5h14', 'M5 12h14', 'M5 16.5h14'],
  close: ['M6 6l12 12', 'M18 6 6 18'],
  folder: [
    'M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z',
  ],
  file: [
    'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z',
    'M14 2v6h6',
  ],
  more: ['M12 7h.01', 'M12 12h.01', 'M12 17h.01'],
  save: ['M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z', 'M17 21v-8H7v8', 'M7 3v5h8'],
  'arrow-left': ['M12 19l-7-7 7-7', 'M19 12H5'],
  'chevron-right': ['M9 18l6-6-6-6'],
  chevron: ['M6 9l6 6 6-6'],
  globe: [
    'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z',
    'M2 12h20',
    'M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10Z',
  ],
  check: ['M20 6 9 17l-5-5'],
  dot: ['M12 12h.01'],
  chat: [
    'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  ],
  settings: [
    'M4 7h4',
    'M4 12h4',
    'M4 17h4',
    'M12 7h8',
    'M12 12h8',
    'M12 17h8',
    'M8 7a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
    'M8 12a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
    'M8 17a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
  ],
  sliders: [
    'M4 7h4',
    'M4 12h4',
    'M4 17h4',
    'M12 7h8',
    'M12 12h8',
    'M12 17h8',
    'M8 7a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
    'M8 12a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
    'M8 17a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
  ],
  play: ['M6 4.5v15l13-7.5L6 4.5Z'],
  eye: [
    'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z',
    'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  ],
  refresh: ['M21 12a9 9 0 1 1-2.6-6.2', 'M21 3v6h-6'],
  copy: [
    'M8 8h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2Z',
    'M4 16V6a2 2 0 0 1 2-2h10',
  ],
  // Keep current tab, dismiss neighbors with X marks
  'close-others': [
    'M10 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z',
    'M3 9l4 4',
    'M7 9l-4 4',
    'M17 9l4 4',
    'M21 9l-4 4',
  ],
  'close-left': [
    'M14 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z',
    'M10 8 6 12l4 4',
    'M6 12h6',
  ],
  'close-right': [
    'M6 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z',
    'M14 8l4 4-4 4',
    'M18 12H12',
  ],
  'close-all': [
    'M5 5h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',
    'M9 9l6 6',
    'M15 9l-6 6',
  ],
  'close-saved': [
    'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z',
    'M14 2v6h6',
    'M9 15l2 2 4-4',
  ],
  rocket: [
    'M4.5 16.5c1.5-1 3.5-1.5 5.5-1 2.2.5 4 2 5 4',
    'M12 15.5c2.5-.5 5-2.5 6.5-6.5 0-2.5-1-5-2.5-6.5-1.5-1.5-4-2.5-6.5-2.5-4 1.5-6 4-6.5 6.5.5 2.5 2.5 5 6.5 6.5Z',
    'M9 12a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
  ],
  clock: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'M12 6v6l4 2'],
  download: [
    'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4',
    'M7 10l5 5 5-5',
    'M12 15V3',
  ],
  'panel-left': [
    'M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z',
    'M9 4v16',
  ],
  'panel-right': [
    'M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z',
    'M15 4v16',
  ],
  'panel-bottom': [
    'M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z',
    'M3 15h18',
  ],
  terminal: [
    'M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z',
    'M8 9l3 3-3 3',
    'M13 15h5',
  ],
  wrench: [
    'M14.7 6.3a4 4 0 0 0-4.9 4.9L4 17v3h3l5.8-5.8a4 4 0 0 0 1.9-7.9Z',
  ],
  trash: [
    'M3 6h18',
    'M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2',
    'M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6',
    'M10 11v6',
    'M14 11v6',
  ],
  pencil: [
    'M12 20h9',
    'M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z',
  ],
  atom: [
    'M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z',
    'M12 4.5c3.5 0 6.5 2.2 7.5 5.5-1 3.3-4 5.5-7.5 5.5S5.5 13.3 4.5 10c1-3.3 4-5.5 7.5-5.5Z',
  ],
  sparkles: [
    'M12 3l1.2 3.2L16.5 7.5 13.2 8.8 12 12l-1.2-3.2L7.5 7.5l3.3-1.3L12 3Z',
    'M19 11l.7 1.8L21.5 14l-1.8.7L19 16.5l-.7-1.8L16.5 14l1.8-.7L19 11Z',
    'M6.5 14l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2Z',
  ],
  upload: [
    'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4',
    'M17 8l-5-5-5 5',
    'M12 3v12',
  ],
  book: [
    'M4 19.5A2.5 2.5 0 0 1 6.5 17H20',
    'M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z',
  ],
  puzzle: [
    'M12 4.5c.8 0 1.5.7 1.5 1.5 0 .5-.3.9-.7 1.2V9h3c.3-.4.7-.7 1.2-.7.8 0 1.5.7 1.5 1.5s-.7 1.5-1.5 1.5c-.5 0-.9-.3-1.2-.7H13.5v3c.4.3.7.7.7 1.2 0 .8-.7 1.5-1.5 1.5s-1.5-.7-1.5-1.5c0-.5.3-.9.7-1.2V12H9c-.3.4-.7.7-1.2.7-.8 0-1.5-.7-1.5-1.5s.7-1.5 1.5-1.5c.5 0 .9.3 1.2.7H12V7.2c-.4-.3-.7-.7-.7-1.2 0-.8.7-1.5 1.5-1.5Z',
  ],
  chip: [
    'M9 9h6v6H9V9Z',
    'M12 2v4',
    'M12 18v4',
    'M2 12h4',
    'M18 12h4',
    'M5.5 5.5 8 8',
    'M16 16l2.5 2.5',
    'M18.5 5.5 16 8',
    'M8 16l-2.5 2.5',
  ],
  git: [
    'M6 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
    'M6 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
    'M18 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
    'M6 8v8',
    'M8.2 7.8 16 12',
  ],
  search: ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z', 'M21 21l-4.3-4.3'],
  'file-plus': [
    'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z',
    'M14 2v6h6',
    'M12 18v-6',
    'M9 15h6',
  ],
  'folder-plus': [
    'M12 10v6',
    'M9 13h6',
    'M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z',
  ],
  'file-edit': [
    'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6',
    'M14 2v6h6',
    'M16.5 11.5a2.1 2.1 0 0 1 3 3L10 22l-4 1 1-4 9.5-7.5Z',
  ],
  alert: ['M10.3 3.8 1.8 18.5A2 2 0 0 0 3.5 21.5h16.9a2 2 0 0 0 1.7-3L13.7 3.8a2 2 0 0 0-3.4 0Z', 'M12 9v4', 'M12 17h.01'],
  think: [
    'M12 3a5 5 0 0 0-3.2 8.9c.5.4.9 1 .9 1.6h5c0-.6.4-1.2.9-1.6A5 5 0 0 0 12 3Z',
    'M10 16h4',
    'M10.5 19h3',
  ],
  zap: ['M13 2 4 14h7l-1 8 9-12h-7l1-8Z'],
}

function glyphs(name: string) {
  const key = aliases[name] || name
  return paths[key] || paths.file
}
</script>

<template>
  <svg
    class="app-icon"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
    :width="size"
    :height="size"
  >
    <path
      v-for="(d, index) in glyphs(props.name)"
      :key="index"
      :d="d"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>

<style scoped>
.app-icon {
  display: block;
  flex-shrink: 0;
}
</style>
