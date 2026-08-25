<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'

const props = defineProps<{
  modelValue: string
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
  emit(ok ? 'commit' : 'cancel')
}

onMounted(() => {
  nextTick(() => {
    input.value?.focus()
    input.value?.select()
  })
})
</script>

<template>
  <div class="mkdir-row">
    <AppIcon name="folder-plus" :size="14" />
    <input
      ref="input"
      class="mkdir-input"
      :value="modelValue"
      placeholder="文件夹名"
      spellcheck="false"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      @keydown.enter.prevent="finish(true)"
      @keydown.escape.prevent="finish(false)"
      @blur="finish(false)"
      @click.stop
    />
    <button type="button" class="mkdir-btn primary" @mousedown.prevent @click="finish(true)">创建</button>
    <button type="button" class="mkdir-btn" @mousedown.prevent @click="finish(false)">取消</button>
  </div>
</template>

<style scoped>
.mkdir-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
}
.mkdir-input {
  flex: 1;
  min-width: 0;
  height: 24px;
  font-size: 13px;
  padding: 0 6px;
  border: 1px solid var(--primary);
  border-radius: 4px;
  background: var(--bg);
  color: var(--text);
  outline: none;
  font-family: inherit;
}
.mkdir-btn {
  height: 24px;
  padding: 0 8px;
  border: 0;
  border-radius: 4px;
  background: var(--code-bg);
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
}
.mkdir-btn:hover { color: var(--text-h); }
.mkdir-btn.primary {
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 600;
}
</style>
