<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/AppIcon.vue'

const props = defineProps<{
  params?: {
    api?: { id?: string; close?: () => void }
    params?: { api?: { id?: string; close?: () => void } }
    title?: string
  }
  api?: { id?: string; close?: () => void }
  title?: string
}>()

const meta: Record<string, { icon: string; label: string }> = {
  workspace: { icon: 'home', label: '工作空间' },
  explorer: { icon: 'folder', label: '文件' },
  editor: { icon: 'file', label: '编辑器' },
  agent: { icon: 'sparkles', label: 'Agent' },
  terminal: { icon: 'terminal', label: '终端' },
  chats: { icon: 'chat', label: '会话' },
  git: { icon: 'git', label: 'Git' },
  skills: { icon: 'book', label: 'Skill' },
  models: { icon: 'chip', label: '模型' },
  settings: { icon: 'sliders', label: '设置' },
  trajectory: { icon: 'clock', label: '轨迹' },
}

const panelApi = computed(() => props.api || props.params?.api || props.params?.params?.api)
const id = computed(() => panelApi.value?.id || '')
const info = computed(() => {
  if (meta[id.value]) return meta[id.value]
  const title = props.title || props.params?.title
  return { icon: 'file', label: title || id.value || '面板' }
})

function close(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  panelApi.value?.close?.()
}
</script>

<template>
  <div class="ptab" :title="info.label">
    <AppIcon :name="info.icon" :size="14" />
    <span class="lbl">{{ info.label }}</span>
    <button type="button" class="x" title="关闭" @mousedown.stop.prevent @click="close">×</button>
  </div>
</template>

<style scoped>
.ptab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 100%;
  padding: 0 2px 0 8px;
  color: inherit;
}
.lbl {
  font-size: 11px;
  font-weight: 600;
  max-width: 72px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: inherit;
}
.x {
  width: 16px;
  height: 16px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  opacity: 0;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}
.ptab:hover .x { opacity: 0.55; }
.x:hover { opacity: 1 !important; background: color-mix(in srgb, currentColor 12%, transparent); }
</style>
