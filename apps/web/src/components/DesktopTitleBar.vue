<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import BrandMark from '@/components/BrandMark.vue'
import { useAppStore } from '@/stores/app'
import { currentTheme, type Theme } from '@/theme'
import { formatWindowTitle, WINDOW_TITLE_APP_NAME } from '@/utils/windowTitle'

const props = defineProps<{
  theme?: Theme
  showActions?: boolean
}>()

const emit = defineEmits<{
  toggleTheme: []
  openCommandPalette: []
}>()

const { t } = useI18n()
const store = useAppStore()

const titleLabel = computed(() => {
  const id = store.conversationId
  const session = id ? store.conversations.find((c) => c.id === id)?.title : null
  const workspace = store.workspace?.name || null
  return formatWindowTitle({ session, workspace })
})

const titleHint = computed(() =>
  titleLabel.value === WINDOW_TITLE_APP_NAME ? WINDOW_TITLE_APP_NAME : titleLabel.value,
)

const resolvedTheme = computed(() => props.theme || currentTheme())
</script>

<template>
  <header class="desktop-titlebar" aria-hidden="false">
    <div class="desktop-titlebar-brand" :title="titleHint">
      <BrandMark :size="18" />
      <span class="desktop-titlebar-name">{{ titleLabel }}</span>
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
          :name="resolvedTheme === 'dark' ? 'sun' : 'moon'"
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
  flex-shrink: 1;
  min-width: 0;
  max-width: min(52vw, 420px);
  -webkit-app-region: drag;
}
.desktop-titlebar-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
  letter-spacing: -0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
