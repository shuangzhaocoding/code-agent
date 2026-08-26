<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'

const { t } = useI18n()

const props = defineProps<{
  params?: {
    api?: { id?: string; close?: () => void }
    params?: { api?: { id?: string; close?: () => void } }
    title?: string
  }
  api?: { id?: string; close?: () => void }
  title?: string
}>()

const icons: Record<string, string> = {
  workspace: 'home',
  explorer: 'folder',
  search: 'search',
  editor: 'file',
  agent: 'atom',
  terminal: 'terminal',
  ports: 'ports',
  chats: 'chat',
  git: 'git',
  skills: 'book',
  plugins: 'puzzle',
  models: 'chip',
  settings: 'sliders',
  trajectory: 'clock',
}

const panelApi = computed(() => props.api || props.params?.api || props.params?.params?.api)
const id = computed(() => panelApi.value?.id || '')
const info = computed(() => {
  const key = `panels.${id.value}`
  const label = t(key)
  if (icons[id.value] && label !== key) return { icon: icons[id.value], label }
  const title = props.title || props.params?.title
  return { icon: icons[id.value] || 'file', label: title || id.value || t('common.panel') }
})

function close(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  panelApi.value?.close?.()
}
</script>

<template>
  <div class="ptab" :title="info.label">
    <AppIcon class="ptab-ico" :name="info.icon" :size="13" />
    <span class="lbl">{{ info.label }}</span>
    <button type="button" class="x" :title="t('common.close')" @mousedown.stop.prevent @click="close">
      <AppIcon name="close" :size="11" />
    </button>
  </div>
</template>

<style scoped>
.ptab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 100%;
  padding: 0 4px 0 9px;
  color: inherit;
}
.ptab-ico {
  opacity: 0.82;
}
.lbl {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.01em;
  max-width: 88px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: inherit;
}
.x {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-left: 2px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  opacity: 0;
  cursor: pointer;
}
.ptab:hover .x { opacity: 0.5; }
.x:hover { opacity: 1 !important; background: color-mix(in srgb, currentColor 14%, transparent); }
</style>
