<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
onMounted(() => store.loadSkills())
</script>

<template>
  <div class="panel-shell">
    <div class="panel-body skills">
      <p>把含 SKILL.md 的目录放到 skills/、~/.code-agent/skills/ 或工作区 .agents/skills/</p>
      <article v-for="s in store.skills" :key="s.name + s.source">
        <h3>{{ s.name }}</h3>
        <small>{{ s.source }}</small>
        <p>{{ s.description }}</p>
        <em v-if="s.invalid_reason">{{ s.invalid_reason }}</em>
      </article>
    </div>
  </div>
</template>

<style scoped>
.skills { padding: 14px 16px; }
p, small { color: var(--text-secondary); margin: 0 0 8px; }
article {
  border-top: 1px solid var(--border);
  padding: 12px 0;
}
h3 { margin: 0 0 4px; font-size: 14px; }
em { color: var(--danger); font-style: normal; font-size: 12px; }
</style>
