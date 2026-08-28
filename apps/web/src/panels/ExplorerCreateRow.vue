<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import FileTreeIcon from '@/components/FileTreeIcon.vue'

defineProps<{
  kind: 'file' | 'dir'
  depth: number
  modelValue: string
  dir: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  commit: []
  cancel: []
}>()

const input = ref<HTMLInputElement | null>(null)
let done = false

function finish(ok: boolean) {
  if (done) return
  done = true
  if (ok) emit('commit')
  else emit('cancel')
}

onMounted(() => {
  nextTick(() => {
    input.value?.focus()
    input.value?.select()
    input.value?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
})
</script>

<template>
  <div class="row create" :style="{ paddingLeft: 8 + depth * 14 + 'px' }">
    <span class="twist hidden" />
    <FileTreeIcon
      :kind="kind === 'dir' ? 'dir' : 'file'"
      :path="dir ? `${dir}/${modelValue || (kind === 'dir' ? 'untitled' : 'untitled.txt')}` : (modelValue || (kind === 'dir' ? 'untitled' : 'untitled.txt'))"
      :size="16"
    />
    <input
      ref="input"
      class="create-input"
      :value="modelValue"
      :placeholder="kind === 'dir' ? '目录名' : '文件名'"
      spellcheck="false"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      @keydown.enter.prevent="finish(true)"
      @keydown.escape.prevent="finish(false)"
      @blur="finish(false)"
      @click.stop
      @contextmenu.stop
    />
    <button type="button" class="create-btn primary" @mousedown.prevent @click.stop="finish(true)">创建</button>
    <button type="button" class="create-btn" @mousedown.prevent @click.stop="finish(false)">取消</button>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 28px;
  padding-right: 8px;
  background: var(--primary-soft);
}
.twist {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  visibility: hidden;
  margin: 0 2px;
}
.create-input {
  flex: 1;
  min-width: 0;
  height: 22px;
  font-size: 13px;
  padding: 0 4px;
  border: 1px solid var(--primary);
  border-radius: 3px;
  background: var(--bg);
  color: var(--text);
  outline: none;
  font-family: inherit;
}
.create-btn {
  height: 22px;
  padding: 0 8px;
  border: 0;
  border-radius: 4px;
  background: var(--code-bg);
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
}
.create-btn:hover { color: var(--text-h); }
.create-btn.primary {
  background: var(--bg);
  color: var(--primary);
  font-weight: 600;
}
</style>
