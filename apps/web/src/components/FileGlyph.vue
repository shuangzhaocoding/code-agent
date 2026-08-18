<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ name: string; isDir?: boolean; size?: number }>()

const kind = computed(() => {
  const n = props.name.toLowerCase()
  if (props.isDir) {
    if (n === 'src' || n === 'lib' || n === 'code' || n === 'app' || n === 'apps') return 'folder-code'
    if (n === 'docs' || n === 'doc') return 'folder-docs'
    if (n === 'public' || n === 'static' || n === 'assets') return 'folder-public'
    if (n === 'scripts' || n === 'bin') return 'folder-scripts'
    if (n === '.cursor' || n === '.vscode') return 'folder-cursor'
    if (n === '.cache' || n === 'cache' || n === 'tmp' || n === 'dist' || n === 'build' || n === 'node_modules') return 'folder-cache'
    if (n.startsWith('.')) return 'folder-dot'
    return 'folder'
  }
  if (n === 'dockerfile' || n === '.dockerignore' || n.endsWith('.dockerfile')) return 'docker'
  if (n === '.gitignore' || n === '.gitattributes' || n === '.gitmodules') return 'git'
  if (n === 'package.json' || n === 'package-lock.json' || n === 'pnpm-lock.yaml' || n === '.npmrc') return 'npm'
  if (n === 'readme.md' || n === 'readme') return 'readme'
  if (n === 'vite.config.ts' || n === 'vite.config.js') return 'vite'
  if (n === 'tsconfig.json' || n.startsWith('tsconfig.')) return 'tsconfig'
  const ext = n.includes('.') ? n.slice(n.lastIndexOf('.') + 1) : ''
  const map: Record<string, string> = {
    ts: 'ts', tsx: 'ts', js: 'js', mjs: 'js', cjs: 'js', jsx: 'js', vue: 'vue', py: 'py',
    md: 'md', json: 'json', html: 'html', htm: 'html', css: 'css', scss: 'css', sass: 'css', less: 'css',
    yaml: 'yaml', yml: 'yaml', sh: 'sh', bash: 'sh', zsh: 'sh', svg: 'image', png: 'image',
    jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', toml: 'toml', xml: 'xml',
    sql: 'sql', go: 'go', rs: 'rs', java: 'java', kt: 'java',
  }
  return map[ext] || 'file'
})
</script>

<template>
  <svg class="file-glyph" :class="kind" :width="size || 16" :height="size || 16" viewBox="0 0 16 16" aria-hidden="true">
    <template v-if="kind === 'folder' || kind === 'folder-dot'">
      <path d="M1.5 4.2h4.2l1.2 1.3H14.5v7.3a1 1 0 0 1-1 1h-12a1 1 0 0 1-1-1V4.2Z" />
    </template>
    <template v-else-if="kind === 'folder-code'">
      <path d="M1.5 4.2h4.2l1.2 1.3H14.5v7.3a1 1 0 0 1-1 1h-12a1 1 0 0 1-1-1V4.2Z" />
      <path d="M6.2 8.2 4.8 9.6 6.2 11M9.8 8.2l1.4 1.4-1.4 1.4" fill="none" stroke="#fff" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" />
    </template>
    <template v-else-if="kind === 'folder-docs'">
      <path d="M1.5 4.2h4.2l1.2 1.3H14.5v7.3a1 1 0 0 1-1 1h-12a1 1 0 0 1-1-1V4.2Z" />
      <path d="M5 9h6M5 11h4" fill="none" stroke="#fff" stroke-width="1.1" stroke-linecap="round" />
    </template>
    <template v-else-if="kind === 'folder-public'">
      <path d="M1.5 4.2h4.2l1.2 1.3H14.5v7.3a1 1 0 0 1-1 1h-12a1 1 0 0 1-1-1V4.2Z" />
      <circle cx="8" cy="10" r="2.2" fill="none" stroke="#fff" stroke-width="1.1" />
    </template>
    <template v-else-if="kind === 'folder-scripts'">
      <path d="M1.5 4.2h4.2l1.2 1.3H14.5v7.3a1 1 0 0 1-1 1h-12a1 1 0 0 1-1-1V4.2Z" />
      <path d="M5.5 8.5 7.2 10 5.5 11.5M8.2 11.5h2.4" fill="none" stroke="#fff" stroke-width="1.1" stroke-linecap="round" />
    </template>
    <template v-else-if="kind === 'folder-cursor'">
      <path d="M1.5 4.2h4.2l1.2 1.3H14.5v7.3a1 1 0 0 1-1 1h-12a1 1 0 0 1-1-1V4.2Z" />
      <path d="M6.2 8.2 10.5 10 6.2 11.8Z" fill="#fff" />
    </template>
    <template v-else-if="kind === 'folder-cache'">
      <path d="M1.5 4.2h4.2l1.2 1.3H14.5v7.3a1 1 0 0 1-1 1h-12a1 1 0 0 1-1-1V4.2Z" />
      <circle cx="8" cy="10" r="2.1" fill="none" stroke="#fff" stroke-width="1.1" />
      <path d="M8 8.6v1.5h1.2" fill="none" stroke="#fff" stroke-width="1.1" stroke-linecap="round" />
    </template>
    <template v-else-if="kind === 'ts'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="7" font-weight="700" fill="#fff">TS</text>
    </template>
    <template v-else-if="kind === 'js'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="7" font-weight="700" fill="#111">JS</text>
    </template>
    <template v-else-if="kind === 'vue'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="6.5" font-weight="700" fill="#fff">V</text>
    </template>
    <template v-else-if="kind === 'py'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="7" font-weight="700" fill="#fff">Py</text>
    </template>
    <template v-else-if="kind === 'md' || kind === 'readme'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="7" font-weight="700" fill="#fff">M</text>
    </template>
    <template v-else-if="kind === 'json' || kind === 'tsconfig'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="6" font-weight="700" fill="#111">{ }</text>
    </template>
    <template v-else-if="kind === 'html'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="6" font-weight="700" fill="#fff">5</text>
    </template>
    <template v-else-if="kind === 'css'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="6" font-weight="700" fill="#fff">#</text>
    </template>
    <template v-else-if="kind === 'yaml' || kind === 'toml'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="7" font-weight="700" fill="#fff">Y</text>
    </template>
    <template v-else-if="kind === 'sh'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <path d="M4.6 6.2 6.8 8 4.6 9.8M7.4 10.2h3.4" fill="none" stroke="#fff" stroke-width="1.2" stroke-linecap="round" />
    </template>
    <template v-else-if="kind === 'docker'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <path d="M4 9h8v1.6H4zM5 7.4h1.4V9H5zm2 0h1.4V9H7zm2 0h1.4V9H9z" fill="#fff" />
    </template>
    <template v-else-if="kind === 'git'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <path d="M8 4.4 11.6 8 8 11.6 4.4 8Z" fill="#fff" />
    </template>
    <template v-else-if="kind === 'npm'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="6.5" font-weight="700" fill="#fff">n</text>
    </template>
    <template v-else-if="kind === 'vite'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <path d="M8 4.2 11.4 12H4.6Z" fill="#fff" />
    </template>
    <template v-else-if="kind === 'image'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <circle cx="6" cy="6.4" r="1.1" fill="#fff" />
      <path d="M3.6 12.2 7 8.6l2 2 1.4-1.6 2 3.2Z" fill="#fff" />
    </template>
    <template v-else-if="kind === 'go'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="6.5" font-weight="700" fill="#fff">Go</text>
    </template>
    <template v-else-if="kind === 'rs'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="7" font-weight="700" fill="#fff">Rs</text>
    </template>
    <template v-else-if="kind === 'java'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="6" font-weight="700" fill="#fff">J</text>
    </template>
    <template v-else-if="kind === 'sql' || kind === 'xml'">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <text x="8" y="11.2" text-anchor="middle" font-size="6" font-weight="700" fill="#fff">&lt;/&gt;</text>
    </template>
    <template v-else>
      <path d="M4 1.8h5.2L12.4 5.2V14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V2.8a1 1 0 0 1 1-1Z" />
      <path d="M9.1 1.8V5.4h3.4" fill="none" stroke="currentColor" stroke-width="1" />
    </template>
  </svg>
</template>

<style scoped>
.file-glyph { flex-shrink: 0; display: block; }
.folder { fill: #dcb15a; }
.folder-dot { fill: #8b93a7; }
.folder-code { fill: #3f9e6b; }
.folder-docs { fill: #3b82f6; }
.folder-public { fill: #2563eb; }
.folder-scripts { fill: #64748b; }
.folder-cursor { fill: #6b7280; }
.folder-cache { fill: #14b8a6; }
.ts, .tsconfig { fill: #3178c6; }
.js { fill: #f7df1e; }
.vue { fill: #41b883; }
.py { fill: #3776ab; }
.md, .readme { fill: #3b82f6; }
.json { fill: #cbcb41; }
.html { fill: #e34f26; }
.css { fill: #c678dd; }
.yaml, .toml { fill: #cb171e; }
.sh { fill: #89e051; }
.docker { fill: #2496ed; }
.git { fill: #f05032; }
.npm { fill: #cb3837; }
.vite { fill: #646cff; }
.image { fill: #d26ac2; }
.go { fill: #00add8; }
.rs { fill: #dea584; }
.java { fill: #b07219; }
.sql, .xml { fill: #e37933; }
.file { fill: #9aa3b2; color: #6b7280; }
</style>
