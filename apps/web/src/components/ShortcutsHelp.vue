<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import { isMacMod, paletteShortcutLabel } from '@/utils/relativeTime'
import { isDesktopApp } from '@/utils/desktop'

const open = defineModel<boolean>('open', { default: false })
const { t } = useI18n()

const mod = isMacMod() ? '⌘' : 'Ctrl+'
const rows = computed(() => {
  const list = [
    { keys: paletteShortcutLabel(), label: t('shortcuts.commandPalette') },
    { keys: isMacMod() ? '⌘K' : 'Ctrl+K', label: t('shortcuts.commandPaletteAlt') },
    { keys: isMacMod() ? '⌘P' : 'Ctrl+P', label: t('shortcuts.openFile') },
    { keys: isMacMod() ? '⌘⇧F' : 'Ctrl+Shift+F', label: t('shortcuts.searchFiles') },
    { keys: `${mod}S`, label: t('shortcuts.save') },
    { keys: `${mod}N`, label: t('shortcuts.newChat') },
  ]
  if (isDesktopApp()) {
    list.push({
      keys: isMacMod() ? '⌘⇧N' : 'Ctrl+Shift+N',
      label: t('shortcuts.newWindow'),
    })
  }
  list.push({ keys: 'Esc', label: t('shortcuts.close') })
  return list
})

function close() {
  open.value = false
}

function onKey(e: KeyboardEvent) {
  if (!open.value) return
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    close()
  }
}

onMounted(() => window.addEventListener('keydown', onKey, true))
onUnmounted(() => window.removeEventListener('keydown', onKey, true))
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="shortcuts-root" @click.self="close">
      <div class="shortcuts-panel" role="dialog" :aria-label="t('shortcuts.title')">
        <header class="shortcuts-head">
          <h2>{{ t('shortcuts.title') }}</h2>
          <button type="button" class="ghost-icon-btn" :title="t('common.close')" @click="close">
            <AppIcon name="close" :size="15" :stroke-width="1.75" />
          </button>
        </header>
        <ul class="shortcuts-list">
          <li v-for="row in rows" :key="row.keys" class="shortcuts-row">
            <span class="shortcuts-label">{{ row.label }}</span>
            <kbd class="shortcuts-keys">{{ row.keys }}</kbd>
          </li>
        </ul>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.shortcuts-root {
  position: fixed;
  inset: 0;
  z-index: 12000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: color-mix(in srgb, #000 36%, transparent);
}
.shortcuts-panel {
  width: min(420px, 100%);
  border: var(--border-width) solid var(--border);
  border-radius: 12px;
  background: var(--panel-bg);
  box-shadow: 0 18px 48px color-mix(in srgb, #000 28%, transparent);
  overflow: hidden;
}
.shortcuts-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 14px 10px;
  border-bottom: var(--border-width) solid var(--border);
}
.shortcuts-head h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 650;
  color: var(--text-h);
}
.shortcuts-list {
  list-style: none;
  margin: 0;
  padding: 8px 0;
}
.shortcuts-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 16px;
}
.shortcuts-label {
  font-size: 13px;
  color: var(--text-h);
}
.shortcuts-keys {
  flex-shrink: 0;
  min-width: 72px;
  padding: 3px 8px;
  border-radius: 6px;
  border: var(--border-width) solid var(--border);
  background: var(--code-bg);
  color: var(--text-secondary);
  font: 600 11px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  text-align: center;
}
</style>
