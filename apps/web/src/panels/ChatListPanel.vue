<script setup lang="ts">
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'

const store = useAppStore()

async function openHistory(id: string) {
  await store.openConversation(id)
  window.dispatchEvent(new Event('ca-focus-agent'))
}

async function startNewChat() {
  await store.newChat()
  window.dispatchEvent(new Event('ca-focus-agent'))
}
</script>

<template>
  <div class="panel-shell">
    <div class="list">
      <button class="btn btn-primary" type="button" @click="startNewChat">
        <AppIcon name="plus" :size="14" />
        新会话
      </button>
      <button
        v-for="c in store.conversations"
        :key="c.id"
        type="button"
        class="menu-item"
        :class="{ active: c.id === store.conversationId }"
        @click="openHistory(c.id)"
      >
        <AppIcon name="chat" :size="14" />
        {{ c.title }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.list {
  display: flex;
  flex-direction: column;
  padding: 10px;
  gap: 2px;
  overflow: auto;
  flex: 1;
}
.btn { width: 100%; margin-bottom: 8px; }
.menu-item { margin-bottom: 0; }
</style>
