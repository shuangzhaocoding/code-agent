<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  patch: string
  binary?: boolean
}>()

const lines = computed(() => (props.patch || '').split('\n'))
</script>

<template>
  <p v-if="binary" class="empty">二进制文件，无法显示文本 diff</p>
  <pre v-else-if="patch" class="diff"><span
    v-for="(line, i) in lines"
    :key="i"
    :class="{
      add: line.startsWith('+') && !line.startsWith('+++'),
      del: line.startsWith('-') && !line.startsWith('---'),
      hunk: line.startsWith('@@'),
      meta: line.startsWith('diff ') || line.startsWith('index ') || line.startsWith('---') || line.startsWith('+++'),
    }"
  >{{ line }}{{ i < lines.length - 1 ? '\n' : '' }}</span></pre>
  <p v-else class="empty">无变更内容</p>
</template>

<style scoped>
.diff {
  margin: 0;
  padding: 8px 10px 12px;
  font-family: var(--mono);
  font-size: 11.5px;
  line-height: 1.45;
  overflow: auto;
  white-space: pre;
  background: var(--code-bg);
}
.diff .add { color: #059669; background: color-mix(in srgb, #059669 10%, transparent); }
.diff .del { color: var(--error-text); background: color-mix(in srgb, var(--error-text) 10%, transparent); }
.diff .hunk { color: var(--primary); }
.diff .meta { color: var(--text-muted); }
:global(html[data-theme='dark']) .diff .add {
  color: #34d399;
  background: color-mix(in srgb, #34d399 12%, transparent);
}
.empty {
  margin: 0;
  padding: 10px 12px;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
