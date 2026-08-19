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
      <article v-for="s in store.skills" :key="s.name + s.source" class="workspace-card">
        <h3>{{ s.name }}</h3>
        <small>{{ s.source }}</small>
        <p>{{ s.description }}</p>
        <em v-if="s.invalid_reason">{{ s.invalid_reason }}</em>
        <span v-else class="status-pill">可用</span>
      </article>
    </div>
  </div>
</template>

<style scoped>
.skills {
  padding: 16px 20px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  align-content: start;
}
.skills > p {
  grid-column: 1 / -1;
  color: var(--text);
  font-size: 13px;
  margin: 0;
}
article h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-h);
}
small, article p { color: var(--text); margin: 0; font-size: 13px; }
em { color: var(--error-text); font-style: normal; font-size: 12px; }
.skills article { cursor: default; }
.skills article:hover { border-color: var(--border); }
</style>
