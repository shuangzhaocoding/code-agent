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

async function removeConversation(id: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  await store.deleteConversation(id)
}
</script>

<template>
  <div class="panel-shell">
    <div class="list">
      <button class="btn btn-primary" type="button" @click="startNewChat">
        <AppIcon name="plus" :size="14" />
        新会话
      </button>
      <div
        v-for="c in store.conversations"
        :key="c.id"
        class="item-wrap"
      >
        <button
          type="button"
          class="menu-item"
          :class="{ active: c.id === store.conversationId }"
          @click="openHistory(c.id)"
        >
          <AppIcon name="chat" :size="14" />
          <span class="item-title">{{ c.title }}</span>
        </button>
        <button
          type="button"
          class="item-delete"
          title="删除会话"
          @click="removeConversation(c.id, $event)"
        >
          <AppIcon name="trash" :size="13" />
        </button>
      </div>
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
.item-wrap {
  position: relative;
  display: flex;
}
.item-wrap:hover .item-delete,
.item-wrap:focus-within .item-delete {
  opacity: 1;
}
.menu-item {
  width: 100%;
  padding-right: 34px;
  margin-bottom: 0;
}
.item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-delete {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
}
.item-delete:hover {
  background: color-mix(in srgb, var(--danger) 12%, var(--code-bg));
  color: var(--danger);
}
</style>
