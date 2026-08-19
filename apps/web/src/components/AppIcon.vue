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
  | 'upload'
  | 'book'
  | 'chip'
  | 'git'
  | 'search'
  | 'file-plus'
  | 'file-edit'
  | 'alert'
  | 'think'
  | 'gear'
  | 'spark'
  | 'layout-left'
  | 'layout-right'
  | 'layout-bottom'
  | 'edit'

const props = defineProps<{
  name: AppIconName | string
  size?: number | string
}>()

const aliases: Record<string, keyof typeof paths> = {
  gear: 'settings',
  spark: 'atom',
  edit: 'pencil',
  'layout-left': 'panel-left',
  'layout-right': 'panel-right',
  'layout-bottom': 'panel-bottom',
}

const paths: Record<string, string[]> = {
  home: [
    'M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5Z',
  ],
  dashboard: [
    'M4 4h7v7H4V4Z',
    'M13 4h7v4h-7V4Z',
    'M13 10h7v10h-7V10Z',
    'M4 13h7v7H4v-7Z',
  ],
  user: [
    'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
    'M5 20a7 7 0 0 1 14 0',
  ],
  users: [
    'M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z',
    'M3.5 20a6.5 6.5 0 0 1 13 0',
    'M17 11a3 3 0 1 0 0-5',
    'M20.5 20a5.5 5.5 0 0 0-3.5-5.1',
  ],
  shield: [
    'M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6l-7-3Z',
  ],
  key: [
    'M8 14a4 4 0 1 1 3.5-5.9L21 17.5 18.5 20 16 17.5 14.5 19',
    'M8 10h.01',
  ],
  sun: [
    'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z',
    'M12 2v2.2',
    'M12 19.8V22',
    'M4.93 4.93l1.56 1.56',
    'M17.51 17.51l1.56 1.56',
    'M2 12h2.2',
    'M19.8 12H22',
    'M4.93 19.07l1.56-1.56',
    'M17.51 6.49l1.56-1.56',
  ],
  moon: [
    'M16.5 13.5A7 7 0 0 1 10 4a7 7 0 1 0 8.5 10.9 5.5 5.5 0 0 1-2-1.4Z',
  ],
  plus: ['M12 5v14', 'M5 12h14'],
  logout: [
    'M10 7V5a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-8a1 1 0 0 1-1-1v-2',
    'M4 12h11',
    'M12 8l4 4-4 4',
  ],
  inbox: [
    'M4 13h4l1.5 2h5L16 13h4',
    'M4 7h16v12H4V7Z',
  ],
  menu: ['M4 7h16', 'M4 12h16', 'M4 17h16'],
  close: ['M6 6l12 12', 'M18 6 6 18'],
  folder: [
    'M3 7h6l2 2h10v10H3V7Z',
  ],
  file: [
    'M7 3h8l5 5v13H7V3Z',
    'M15 3v5h5',
  ],
  more: ['M12 6.5h.01', 'M12 12h.01', 'M12 17.5h.01'],
  save: [
    'M5 4h11l3 3v13H5V4Z',
    'M8 4v5h7V4',
    'M8 20v-6h8v6',
  ],
  'arrow-left': ['M15 6l-6 6 6 6', 'M9 12h10'],
  'chevron-right': ['M9 6l6 6-6 6'],
  chevron: ['M8 10l4 4 4-4'],
  globe: [
    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z',
    'M3 12h18',
    'M12 3c2.5 2.8 3.8 6 3.8 9s-1.3 6.2-3.8 9c-2.5-2.8-3.8-6-3.8-9S9.5 5.8 12 3Z',
  ],
  check: ['M5 12.5 9.5 17 19 7.5'],
  dot: ['M12 12h.01'],
  chat: [
    'M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-4 4v-4H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z',
  ],
  settings: [
    'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
    'M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z',
  ],
  play: ['M8 6v12l11-6Z'],
  eye: [
    'M2.5 12s3.6-7 9.5-7 9.5 7 9.5 7-3.6 7-9.5 7-9.5-7-9.5-7Z',
    'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  ],
  refresh: [
    'M20 12a8 8 0 1 1-2.3-5.7',
    'M20 5v5h-5',
  ],
  copy: [
    'M8 8h11v12H8V8Z',
    'M5 16H4V4h11v1',
  ],
  'close-others': [
    'M9 6h6v12H9V6Z',
    'M4 9l3 6',
    'M7 9l-3 6',
    'M17 9l3 6',
    'M20 9l-3 6',
  ],
  'close-left': [
    'M14 6h4v12h-4',
    'M10 8 5 12l5 4',
    'M5 12h7',
  ],
  'close-right': [
    'M6 6h4v12H6',
    'M14 8l5 4-5 4',
    'M19 12H12',
  ],
  'close-all': [
    'M5 5h14v14H5V5Z',
    'M9 9l6 6',
    'M15 9l-6 6',
  ],
  'close-saved': [
    'M7 3h8l5 5v13H7V3Z',
    'M15 3v5h5',
    'M9.5 14.5 11.5 16.5 16 12',
  ],
  rocket: [
    'M12 3c3 2.2 5 6 5 10.2 0 2.4-1 4.4-2.4 5.8L12 21l-2.6-2c-1.4-1.4-2.4-3.4-2.4-5.8C7 9 9 5.2 12 3Z',
    'M10 14.5 7 18',
    'M14 14.5 17 18',
    'M12 11.2a1.2 1.2 0 1 0 0-2.4 1.2 1.2 0 0 0 0 2.4Z',
  ],
  clock: [
    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z',
    'M12 7v5.5l3.5 2',
  ],
  download: [
    'M12 4v11',
    'M8 11l4 4 4-4',
    'M5 19h14',
  ],
  'panel-left': [
    'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',
    'M9 5v14',
  ],
  'panel-right': [
    'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',
    'M15 5v14',
  ],
  'panel-bottom': [
    'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',
    'M4 14h16',
  ],
  terminal: [
    'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',
    'M7 9l3 3-3 3',
    'M12 15h5',
  ],
  wrench: [
    'M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.5-2.5 2.5-2.5Z',
  ],
  trash: [
    'M4 7h16',
    'M9 7V5h6v2',
    'M7 7l1 12h8l1-12',
    'M10 11v5',
    'M14 11v5',
  ],
  pencil: [
    'M13 5.5 18.5 11',
    'M4 20l4.2-1.1L19 8.1 15.9 5 5.1 15.8 4 20Z',
  ],
  atom: [
    'M12 12.5a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z',
    'M12 4c3.5 0 6.5 2.2 7.5 5.5-1 3.3-4 5.5-7.5 5.5S5.5 12.8 4.5 9.5C5.5 6.2 8.5 4 12 4Z',
    'M7.2 6.2c2.5-2.5 6.3-2.8 9.1-.8 2.8 2 3.6 5.7 1.8 8.7-1.8 3-5.5 4.3-8.7 3.1C6.2 15.9 4.7 12.3 5.4 9c.3-1.1.9-2.1 1.8-2.8Z',
    'M16.8 6.2c-2.5-2.5-6.3-2.8-9.1-.8-2.8 2-3.6 5.7-1.8 8.7 1.8 3 5.5 4.3 8.7 3.1 3.2-1.3 4.7-4.9 4-8.2-.3-1.1-.9-2.1-1.8-2.8Z',
  ],
  upload: [
    'M12 16V7',
    'M8 10l4-4 4 4',
    'M5 18h14',
  ],
  book: [
    'M5 5a2 2 0 0 1 2-2h12v16H7a2 2 0 0 0-2 2',
    'M5 19a2 2 0 0 1 2-2h12',
  ],
  chip: [
    'M8 8h8v8H8V8Z',
    'M10 3.5V8',
    'M14 3.5V8',
    'M10 16v4.5',
    'M14 16v4.5',
    'M3.5 10H8',
    'M3.5 14H8',
    'M16 10h4.5',
    'M16 14h4.5',
  ],
  git: [
    'M6 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
    'M6 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
    'M18 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
    'M6 8v8',
    'M7.6 7.6 16.2 11.2',
  ],
  search: [
    'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z',
    'M16.5 16.5 21 21',
  ],
  'file-plus': [
    'M7 3h8l5 5v13H7V3Z',
    'M15 3v5h5',
    'M12 12v6',
    'M9 15h6',
  ],
  'file-edit': [
    'M7 3h8l5 5v4',
    'M15 3v5h5',
    'M4 20l4.2-1.1L19 8.1 15.9 5 5.1 15.8 4 20Z',
  ],
  alert: [
    'M12 4 3.8 20h16.4L12 4Z',
    'M12 10v5',
    'M12 17.5h.01',
  ],
  think: [
    'M12 4a5.5 5.5 0 0 0-3.1 10.1c.5.4.8 1 .9 1.6h4.4c.1-.6.4-1.2.9-1.6A5.5 5.5 0 0 0 12 4Z',
    'M10 17.8h4',
    'M10.5 20h3',
  ],
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
    :width="size ?? 16"
    :height="size ?? 16"
  >
    <path
      v-for="(d, index) in glyphs(props.name)"
      :key="index"
      :d="d"
      stroke="currentColor"
      stroke-width="1.7"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>
