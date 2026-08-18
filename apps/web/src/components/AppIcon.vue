<script setup lang="ts">
defineProps<{ name: string; size?: number }>()
</script>

<template>
  <svg class="app-icon" :width="size || 16" :height="size || 16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <template v-if="name === 'folder'">
      <path d="M3.5 7.5h6l1.6 1.8H20.5v9.2a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 18.5V7.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'chat'">
      <path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-4 3v-3H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'spark'">
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.2 6.2l2.8 2.8M15 15l2.8 2.8M17.8 6.2 15 9M9 15l-2.8 2.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
    </template>
    <template v-else-if="name === 'terminal'">
      <rect x="3.5" y="5" width="17" height="14" rx="2" stroke="currentColor" stroke-width="1.8" />
      <path d="m7 10 3 2-3 2M12 14h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'book'">
      <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v16H7.5A2.5 2.5 0 0 0 5 21.5V5.5Z" stroke="currentColor" stroke-width="1.8" />
      <path d="M5 18.5A2.5 2.5 0 0 1 7.5 16H19" stroke="currentColor" stroke-width="1.8" />
    </template>
    <template v-else-if="name === 'chip'">
      <rect x="7" y="7" width="10" height="10" rx="1.5" stroke="currentColor" stroke-width="1.8" />
      <path d="M10 3.5v3.5M14 3.5v3.5M10 17v3.5M14 17v3.5M3.5 10H7M3.5 14H7M17 10h3.5M17 14h3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
    </template>
    <template v-else-if="name === 'gear'">
      <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8" />
      <path d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6 6l1.6 1.6M16.4 16.4 18 18M18 6l-1.6 1.6M7.6 16.4 6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
    </template>
    <template v-else-if="name === 'sun'">
      <circle cx="12" cy="12" r="3.5" stroke="currentColor" stroke-width="1.8" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.5 1.5M16.9 16.9l1.5 1.5M18.4 5.6l-1.5 1.5M7.1 16.9 5.6 18.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
    </template>
    <template v-else-if="name === 'moon'">
      <path d="M16.5 13.5A6.5 6.5 0 1 1 10.5 5 5 5 0 0 0 16.5 13.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'refresh'">
      <path d="M20 12a8 8 0 1 1-2.2-5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      <path d="M20 5v5h-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'search'">
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" stroke-width="1.8" />
      <path d="m16 16 4.2 4.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
    </template>
    <template v-else-if="name === 'plus'">
      <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
    </template>
    <template v-else-if="name === 'file'">
      <path d="M7 3.5h7.2L19.5 9v11.5A1.5 1.5 0 0 1 18 22H7a1.5 1.5 0 0 1-1.5-1.5v-17A1.5 1.5 0 0 1 7 3.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
      <path d="M14 3.5V9h5.5" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'layout-left'">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" stroke="currentColor" stroke-width="1.8" />
      <path d="M9 4.5v15" stroke="currentColor" stroke-width="1.8" />
      <path d="M4.4 5.4h4.2v13.2H4.4z" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'layout-bottom'">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" stroke="currentColor" stroke-width="1.8" />
      <path d="M3.5 14h17" stroke="currentColor" stroke-width="1.8" />
      <path d="M4.4 14.4h15.2v4.1a1.1 1.1 0 0 1-1.1 1H5.5a1.1 1.1 0 0 1-1.1-1v-4.1Z" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'layout-right'">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" stroke="currentColor" stroke-width="1.8" />
      <path d="M15 4.5v15" stroke="currentColor" stroke-width="1.8" />
      <path d="M15.4 5.4h4.2v13.2h-4.2z" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'think'">
      <circle cx="12" cy="10" r="5.2" stroke="currentColor" stroke-width="1.8" />
      <path d="M9.2 15.6c.6 1.6 1.4 2.6 2.8 2.6s2.2-1 2.8-2.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      <path d="M10.2 9.2h.2M13.6 9.2h.2M10.6 11.6c.8.7 2 .7 2.8 0" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
    </template>
    <template v-else-if="name === 'logout'">
      <path d="M10 5H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4M14 16l5-4-5-4M19 12H10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'chevron'">
      <path d="m8 10 4 4 4-4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'wrench'">
      <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 0 5.4-5.4L16 11l-3-3 1.7-1.7Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'edit'">
      <path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17v3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
      <path d="m14.5 6.5 3 3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
    </template>
    <template v-else-if="name === 'trash'">
      <path d="M5 7h14M10 7V5h4v2M8 7l.8 12h6.4L16 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'eye'">
      <path d="M3 12s3.5-6.5 9-6.5S21 12 21 12s-3.5 6.5-9 6.5S3 12 3 12Z" stroke="currentColor" stroke-width="1.8" />
      <circle cx="12" cy="12" r="2.4" stroke="currentColor" stroke-width="1.8" />
    </template>
    <template v-else-if="name === 'file-plus'">
      <path d="M7 3.5h7.2L19.5 9v11.5A1.5 1.5 0 0 1 18 22H7a1.5 1.5 0 0 1-1.5-1.5v-17A1.5 1.5 0 0 1 7 3.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
      <path d="M14 3.5V9h5.5M12 13v6M9 16h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'file-edit'">
      <path d="M7 3.5h6.5L18 8v4" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
      <path d="M13.5 3.5V8H18M6.5 20.5h4L18 13l-3-3-7.5 7.5v3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
    </template>
    <template v-else-if="name === 'alert'">
      <path d="M12 4 3.8 19h16.4L12 4Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
      <path d="M12 10v4.5M12 17.2v.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
    </template>
    <template v-else-if="name === 'git'">
      <circle cx="6" cy="18" r="2.4" stroke="currentColor" stroke-width="1.8" />
      <circle cx="6" cy="6" r="2.4" stroke="currentColor" stroke-width="1.8" />
      <circle cx="18" cy="12" r="2.4" stroke="currentColor" stroke-width="1.8" />
      <path d="M6 8.4v7.2M7.8 7.2 16.2 11.2" stroke="currentColor" stroke-width="1.8" />
    </template>
    <template v-else-if="name === 'check'">
      <path d="m5.5 12.5 4.2 4.2 8.8-9.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </template>
    <template v-else>
      <circle cx="12" cy="12" r="7" stroke="currentColor" stroke-width="1.8" />
    </template>
  </svg>
</template>
