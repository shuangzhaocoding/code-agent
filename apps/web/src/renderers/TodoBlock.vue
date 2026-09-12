<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Block } from '@/protocol/applyEvent'
import AppIcon from '@/components/AppIcon.vue'

type TodoStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'
type TodoItem = { id: string; content: string; status: TodoStatus }

const props = defineProps<{ block: Block }>()
const { t } = useI18n()

const items = computed<TodoItem[]>(() => {
  const raw = props.block.meta?.items
  if (Array.isArray(raw)) {
    return raw
      .map((row, index) => {
        if (!row || typeof row !== 'object') return null
        const rec = row as Record<string, unknown>
        const status = String(rec.status || 'pending') as TodoStatus
        const content = String(rec.content || rec.text || '').trim()
        if (!content) return null
        return {
          id: String(rec.id || index + 1),
          content,
          status: ['pending', 'in_progress', 'completed', 'cancelled'].includes(status) ? status : 'pending',
        }
      })
      .filter((row): row is TodoItem => Boolean(row))
  }
  const text = String(props.block.text || '')
  return text
    .split('\n')
    .map((line, index) => {
      const match = line.match(/^\s*\[(?<mark>[ xX>\-])\]\s*(?<content>.+)$/)
      if (!match?.groups?.content) return null
      const mark = match.groups.mark
      const status: TodoStatus =
        mark === 'x' || mark === 'X' ? 'completed' : mark === '>' ? 'in_progress' : mark === '-' ? 'cancelled' : 'pending'
      return { id: String(index + 1), content: match.groups.content, status }
    })
    .filter((row): row is TodoItem => Boolean(row))
})

const counts = computed(() => {
  const total = items.value.length
  const done = items.value.filter((item) => item.status === 'completed' || item.status === 'cancelled').length
  const active = items.value.find((item) => item.status === 'in_progress')
  return { total, done, active }
})
</script>

<template>
  <div class="todo" :class="{ streaming: block.status === 'streaming' }">
    <div class="todo-head">
      <AppIcon name="list" :size="14" :stroke-width="1.75" />
      <span class="todo-kicker">{{ t('chat.todoTitle') }}</span>
      <span class="todo-count">{{ t('chat.todoProgress', { done: counts.done, total: counts.total }) }}</span>
    </div>
    <ol v-if="items.length" class="todo-list">
      <li v-for="item in items" :key="item.id" class="todo-item" :class="item.status">
        <span class="todo-mark" :aria-label="item.status">
          <AppIcon v-if="item.status === 'completed'" name="check" :size="12" :stroke-width="2" />
          <AppIcon v-else-if="item.status === 'in_progress'" name="loader" :size="12" :stroke-width="1.75" />
          <AppIcon v-else-if="item.status === 'cancelled'" name="minus" :size="12" :stroke-width="2" />
        </span>
        <span class="todo-text">{{ item.content }}</span>
      </li>
    </ol>
    <p v-else class="todo-empty">{{ t('chat.todoEmpty') }}</p>
  </div>
</template>

<style scoped>
.todo {
  margin: 2px 0 8px;
  padding: 8px 10px 6px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
}
.todo-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  color: var(--text-muted);
}
.todo-kicker {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.todo-count {
  margin-left: auto;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.todo-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 2px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-h);
}
.todo-mark {
  width: 16px;
  height: 16px;
  margin-top: 1px;
  flex-shrink: 0;
  border-radius: 4px;
  border: 1px solid var(--border-strong);
  display: grid;
  place-items: center;
  color: var(--text-muted);
}
.todo-item.completed .todo-mark {
  border-color: color-mix(in srgb, var(--ok) 45%, var(--border));
  background: color-mix(in srgb, var(--ok) 12%, var(--surface));
  color: var(--ok);
}
.todo-item.in_progress .todo-mark {
  border-color: color-mix(in srgb, var(--primary) 50%, var(--border));
  color: var(--primary);
}
.todo-item.in_progress .todo-mark :deep(svg) {
  animation: todo-spin 0.9s linear infinite;
}
.todo-item.completed .todo-text {
  color: var(--text-muted);
}
.todo-item.cancelled .todo-text {
  color: var(--text-muted);
  text-decoration: line-through;
}
.todo-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}
@keyframes todo-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
