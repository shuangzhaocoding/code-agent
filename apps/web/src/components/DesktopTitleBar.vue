<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import BrandMark from '@/components/BrandMark.vue'
import { currentTheme, type Theme } from '@/theme'

defineProps<{
  theme?: Theme
  showActions?: boolean
}>()

const emit = defineEmits<{
  toggleTheme: []
  openCommandPalette: []
}>()

const { t } = useI18n()
</script>

<template>
  <header class="desktop-titlebar" aria-hidden="false">
    <div class="desktop-titlebar-brand" title="Code Agent">
      <BrandMark :size="18" />
      <span class="desktop-titlebar-name">Code Agent</span>
    </div>
    <div class="desktop-titlebar-drag" />
    <div v-if="showActions" class="desktop-titlebar-actions">
      <button
        type="button"
        class="ghost-icon-btn"
        :title="t('menu.items.commandPalette')"
        @click="emit('openCommandPalette')"
      >
        <AppIcon name="search" :size="15" :stroke-width="1.75" />
      </button>
      <button
        type="button"
        class="ghost-icon-btn"
        :title="t('theme.toggle')"
        @click="emit('toggleTheme')"
      >
        <AppIcon
          :name="(theme || currentTheme()) === 'dark' ? 'sun' : 'moon'"
          :size="15"
          :stroke-width="1.75"
        />
      </button>
    </div>
  </header>
</template>

<style scoped>
.desktop-titlebar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  height: var(--desktop-titlebar-height, 38px);
  padding: 0 10px;
  background: var(--sidebar-bg);
  border-bottom: var(--border-width) solid var(--border);
  user-select: none;
  -webkit-app-region: drag;
}
.desktop-titlebar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  -webkit-app-region: drag;
}
.desktop-titlebar-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
  letter-spacing: -0.02em;
  white-space: nowrap;
}
.desktop-titlebar-drag {
  flex: 1;
  min-width: 24px;
  align-self: stretch;
  -webkit-app-region: drag;
}
.desktop-titlebar-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  -webkit-app-region: no-drag;
}
</style>
