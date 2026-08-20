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
  close: ['M7 7l10 10', 'M17 7 7 17'],
  folder: ['M4 7.5h6l1.5 1.5H20v9.5H4V7.5Z'],
  file: ['M8 4.5h7.5L19 8v11.5H8V4.5Z', 'M15 4.5V8H19'],
  more: ['M12 7h.01', 'M12 12h.01', 'M12 17h.01'],
  save: ['M6 5.5h10l2.5 2.5V19H6V5.5Z', 'M9 5.5V10h6V5.5', 'M9 19v-5h6v5'],
  'arrow-left': ['M14.5 7.5 9 12l5.5 4.5', 'M9 12h10'],
  'chevron-right': ['M9.5 7.5 15 12l-5.5 4.5'],
  chevron: ['M8.5 10l3.5 3.5L15.5 10'],
  globe: ['M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17Z', 'M3.5 12h17', 'M12 3.5c2.2 2.5 3.3 5.2 3.3 8.5s-1.1 6-3.3 8.5c-2.2-2.5-3.3-5.2-3.3-8.5s1.1-6 3.3-8.5Z'],
  check: ['M5.5 12.5 9.5 16.5 19 7'],
  dot: ['M12 12h.01'],
  chat: ['M6 6.5h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H10l-3.5 3v-3H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z'],
  settings: ['M5 7h3', 'M5 12h3', 'M5 17h3', 'M11 7h8', 'M11 12h8', 'M11 17h8', 'M6.5 7a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z', 'M6.5 12a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z', 'M6.5 17a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z'],
  sliders: ['M5 7h3', 'M5 12h3', 'M5 17h3', 'M11 7h8', 'M11 12h8', 'M11 17h8', 'M6.5 7a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z', 'M6.5 12a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z', 'M6.5 17a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z'],
  play: ['M9 7.5v9l8.5-4.5L9 7.5Z'],
  eye: ['M3 12s3.5-6.5 9-6.5 9 6.5 9 6.5-3.5 6.5-9 6.5S3 12 3 12Z', 'M12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z'],
  refresh: ['M19 12a7 7 0 1 1-2-5', 'M19 5.5V10h-4.5'],
  copy: ['M9 9.5h9.5V19H9V9.5Z', 'M6.5 15.5H5.5V5.5H15V6.5'],
  'close-others': ['M9.5 6.5h5v11h-5v-11Z', 'M4.5 10l2.5 4', 'M7 10l-2.5 4', 'M19.5 10l-2.5 4', 'M17 10l2.5 4'],
  'close-left': ['M14.5 6.5h3.5v11h-3.5', 'M10.5 8.5 6.5 12l4 3.5', 'M6.5 12h6.5'],
  'close-right': ['M6 6.5h3.5v11H6', 'M13.5 8.5l4 3.5-4 3.5', 'M17.5 12H11'],
  'close-all': ['M5.5 5.5h13v13h-13v-13Z', 'M9.5 9.5l5 5', 'M14.5 9.5l-5 5'],
  'close-saved': ['M8 4.5h7.5L19 8v11.5H8V4.5Z', 'M15 4.5V8H19', 'M10 14.5 12 16.5 16.5 12'],
  rocket: ['M12 4.5c2.8 2 4.5 5.2 4.5 9.2 0 2-0.8 3.8-2 5L12 20.5l-2.5-1.8c-1.2-1.2-2-3-2-5 0-4 1.7-7.2 4.5-9.2Z', 'M10 14.5 7.5 17.5', 'M14 14.5l2.5 3', 'M12 11.5v.01'],
  clock: ['M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17Z', 'M12 7v5.5l3.5 2'],
  download: ['M12 4.5v10', 'M8.5 11 12 14.5 15.5 11', 'M5.5 18.5h13'],
  'panel-left': ['M5 5.5h14a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1Z', 'M9.5 5.5v13'],
  'panel-right': ['M5 5.5h14a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1Z', 'M14.5 5.5v13'],
  'panel-bottom': ['M5 5.5h14a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1Z', 'M5 14.5h14'],
  terminal: ['M5 5.5h14a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1Z', 'M8 10l2.5 2.5L8 15', 'M12.5 15h5'],
  wrench: ['M14.5 6.5a3.5 3.5 0 0 0-4.8 4.8L5 16v3h3l4.7-4.7a3.5 3.5 0 0 0 1.8-7.8Z'],
  trash: ['M5.5 7.5h13', 'M9.5 7.5V6h5v1.5', 'M7.5 7.5l.8 10.5h7.4l.8-10.5', 'M10 11v4.5', 'M14 11v4.5'],
  pencil: ['M13.5 5.5 18.5 10.5', 'M5 19l3.8-1 9.5-9.5-3.8-3.8L5 15.2V19Z'],
  atom: ['M12 12.5a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z', 'M12 5.5c3 0 5.5 1.8 6.5 4.5-1 2.7-3.5 4.5-6.5 4.5s-5.5-1.8-6.5-4.5c1-2.7 3.5-4.5 6.5-4.5Z'],
  sparkles: ['M12 3.5l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3Z', 'M18.5 6.5l.5 1.5 1.5.5-1.5.5-.5 1.5-.5-1.5-1.5-.5 1.5-.5.5-1.5Z', 'M6 8l.7 2.1 2.1.7-2.1.7L6 13.5 5.3 11.4 3.2 10.7l2.1-.7L6 8Z'],
  upload: ['M12 15.5V7.5', 'M8.5 10.5 12 7l3.5 3.5', 'M5.5 17.5h13'],
  book: ['M6 5.5a1.5 1.5 0 0 1 1.5-1.5H19v13H7.5A1.5 1.5 0 0 0 6 18.5', 'M6 18.5A1.5 1.5 0 0 1 7.5 17H19'],
  // Jigsaw piece — common “skills / plugins” metaphor
  puzzle: [
    'M12 4.5c.8 0 1.5.7 1.5 1.5 0 .5-.3.9-.7 1.2V9h3c.3-.4.7-.7 1.2-.7.8 0 1.5.7 1.5 1.5s-.7 1.5-1.5 1.5c-.5 0-.9-.3-1.2-.7H13.5v3c.4.3.7.7.7 1.2 0 .8-.7 1.5-1.5 1.5s-1.5-.7-1.5-1.5c0-.5.3-.9.7-1.2V12H9c-.3.4-.7.7-1.2.7-.8 0-1.5-.7-1.5-1.5s.7-1.5 1.5-1.5c.5 0 .9.3 1.2.7H12V7.2c-.4-.3-.7-.7-.7-1.2 0-.8.7-1.5 1.5-1.5Z',
  ],
  chip: ['M9 9.5h6v6H9v-6Z', 'M12 4v3.5', 'M12 16.5V20', 'M4 12h3.5', 'M16.5 12H20', 'M6.5 6.5l2.5 2.5', 'M15 15l2.5 2.5', 'M17.5 6.5 15 9', 'M9 15l-2.5 2.5'],
  git: ['M6.5 8.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z', 'M6.5 18.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z', 'M17.5 13.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z', 'M6.5 8.5v7.5', 'M8 8l7.5 4'],
  search: ['M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Z', 'M15.5 15.5 20 20'],
  'file-plus': ['M8 4.5h7.5L19 8v11.5H8V4.5Z', 'M15 4.5V8H19', 'M12 12.5v5', 'M9.5 15h5'],
  'file-edit': ['M8 4.5h7.5L19 8v4', 'M15 4.5V8H19', 'M5 19l3.8-1 9.5-9.5-3.8-3.8L5 15.2V19Z'],
  alert: ['M12 5.5 4.5 18.5h15L12 5.5Z', 'M12 10.5v4', 'M12 16.5h.01'],
  think: ['M12 5a4.5 4.5 0 0 0-2.5 8.2c.4.3.7.8.8 1.3h3.4c.1-.5.4-1 .8-1.3A4.5 4.5 0 0 0 12 5Z', 'M10 16.5h4', 'M10.5 18.5h3'],
  zap: ['M13 3.5 6 14h6l-1 6.5 7-10.5h-6l1-6.5Z'],
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
      stroke-width="1.625"
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
