<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import { useSessionPins } from '@/composables/useSessionPins'
import { formatRelativeTime } from '@/utils/relativeTime'

const store = useAppStore()
const query = ref('')
const pins = useSessionPins()

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const matched = q
    ? store.conversations.filter((c) => c.title.toLowerCase().includes(q))
    : store.conversations
  return [...matched].sort((a, b) => {
    const pa = pins.isPinned(a.id) ? 0 : 1
    const pb = pins.isPinned(b.id) ? 0 : 1
    if (pa !== pb) return pa - pb
    if (pins.isPinned(a.id) && pins.isPinned(b.id)) {
      return pins.ids.value.indexOf(a.id) - pins.ids.value.indexOf(b.id)
    }
    return 0
  })
})

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

function onTogglePin(id: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  pins.toggle(id)
}
</script>

<template>
  <div class="panel-shell">
    <div class="list">
      <button class="btn btn-primary" type="button" @click="startNewChat">
        <AppIcon name="plus" :size="16" :stroke-width="1.75" />
        新会话
      </button>
      <div v-if="store.conversations.length" class="search">
        <AppIcon name="search" :size="16" :stroke-width="1.75" />
        <input v-model="query" type="search" placeholder="搜索会话" />
      </div>
      <div
        v-for="c in filtered"
        :key="c.id"
        class="item-wrap"
        :class="{ pinned: pins.isPinned(c.id) }"
      >
        <button
          type="button"
          class="menu-item"
          :class="{ active: c.id === store.conversationId }"
          :title="c.title"
          @click="openHistory(c.id)"
        >
          <AppIcon name="chat" :size="16" :stroke-width="1.75" />
          <span class="item-copy">
            <span class="item-title">{{ c.title }}</span>
            <span v-if="c.updated_at || c.created_at" class="item-time">{{ formatRelativeTime(c.updated_at || c.created_at) }}</span>
          </span>
        </button>
        <div class="item-actions">
          <button
            type="button"
            class="ghost-icon-btn item-action"
            :class="{ on: pins.isPinned(c.id) }"
            :title="pins.isPinned(c.id) ? '取消置顶' : '置顶'"
            @click="onTogglePin(c.id, $event)"
          >
            <AppIcon name="pin" :size="16" :stroke-width="1.75" />
          </button>
          <button
            type="button"
            class="ghost-icon-btn item-action danger"
            title="删除会话"
            @click="removeConversation(c.id, $event)"
          >
            <AppIcon name="trash" :size="16" :stroke-width="1.75" />
          </button>
        </div>
      </div>
      <p v-if="store.conversations.length && !filtered.length" class="empty">没有匹配的会话</p>
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
.search {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  padding: 0 8px;
  height: 30px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel-bg);
  color: var(--text-muted);
}
.search input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-h);
  outline: none;
  font-size: 12px;
}
.item-wrap {
  position: relative;
  display: flex;
}
.item-wrap:hover .item-actions,
.item-wrap:focus-within .item-actions,
.item-wrap.pinned .item-actions {
  opacity: 1;
}
.menu-item {
  width: 100%;
  padding-right: 58px;
  margin-bottom: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.item-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-time {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 400;
}
.item-actions {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.item-action {
  opacity: 1;
}
.item-action.on { color: var(--primary); opacity: 1; }
.item-action.danger:hover {
  color: var(--danger);
  opacity: 1;
}
.empty {
  margin: 8px;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
