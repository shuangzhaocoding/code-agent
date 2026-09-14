<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Block } from '@/protocol/applyEvent'
import AppIcon from '@/components/AppIcon.vue'

type TodoStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'
type TodoItem = { id: string; content: string; status: TodoStatus }
/** Visual overall state for the checklist card. */
type OverallStatus = 'empty' | 'in_progress' | 'completed' | 'failed' | 'interrupted' | 'cancelled' | 'partial' | 'incomplete'
type RunOutcome = 'completed' | 'failed' | 'cancelled'

const props = withDefaults(
  defineProps<{
    block: Block
    /** Start collapsed (e.g. finished message in timeline). */
    defaultCollapsed?: boolean
    /** Parent run still active — forces “进行中”. */
    live?: boolean
  }>(),
  { defaultCollapsed: undefined, live: false },
)

const { t } = useI18n()

function initialCollapsed(): boolean {
  if (props.defaultCollapsed != null) return props.defaultCollapsed
  return Boolean(props.block.status && props.block.status !== 'streaming')
}

const collapsed = ref(initialCollapsed())

watch(
  () => [props.defaultCollapsed, props.block.status, props.live] as const,
  () => {
    if (props.defaultCollapsed != null) {
      collapsed.value = props.defaultCollapsed
      return
    }
    if (props.live || props.block.status === 'streaming') collapsed.value = false
  },
)

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

const tallies = computed(() => {
  const list = items.value
  const counts = { pending: 0, in_progress: 0, completed: 0, cancelled: 0, total: list.length }
  for (const item of list) counts[item.status] += 1
  return counts
})

const runOutcome = computed<RunOutcome | null>(() => {
  const raw = String(props.block.meta?.outcome || '')
  if (raw === 'completed' || raw === 'failed' || raw === 'cancelled') return raw
  return null
})

const sealed = computed(() => !props.live && props.block.status !== 'streaming')

const overall = computed<OverallStatus>(() => {
  const c = tallies.value
  if (!c.total) return 'empty'

  // While the run is live, always “进行中” even if items lag.
  if (props.live || props.block.status === 'streaming') return 'in_progress'

  if (c.completed === c.total) return 'completed'
  if (c.cancelled === c.total) return 'cancelled'

  // Prefer explicit run outcome after stop / error.
  if (runOutcome.value === 'cancelled') return 'interrupted'
  if (runOutcome.value === 'failed') return 'failed'

  // Finished with leftover work (no outcome, or completed run but todos unfinished).
  if (c.in_progress > 0 || c.pending > 0) {
    return runOutcome.value === 'completed' ? 'incomplete' : 'failed'
  }
  if (c.cancelled > 0 && c.completed > 0) return 'partial'
  return 'incomplete'
})

const overallLabel = computed(() => {
  const map: Record<OverallStatus, string> = {
    empty: 'chat.todoEmpty',
    in_progress: 'chat.todoStatusRunning',
    completed: 'chat.todoStatusAllDone',
    failed: 'chat.todoStatusFailed',
    interrupted: 'chat.todoStatusInterrupted',
    cancelled: 'chat.todoStatusCancelled',
    partial: 'chat.todoStatusPartial',
    incomplete: 'chat.todoStatusIncomplete',
  }
  return t(map[overall.value])
})

const progressLabel = computed(() =>
  t('chat.todoProgress', { done: tallies.value.completed, total: tallies.value.total }),
)

const summaryLine = computed(() => {
  if (!sealed.value) {
    const active = items.value.find((item) => item.status === 'in_progress')
    if (active) return active.content
  }
  const pending = items.value.find((item) => item.status === 'pending' || item.status === 'in_progress')
  if (pending) return pending.content
  return items.value[items.value.length - 1]?.content || ''
})

/** Display label for a row after the run has sealed (stop / fail / complete). */
function itemStatusLabel(status: TodoStatus): string {
  if (!sealed.value) {
    if (status === 'completed') return t('chat.todoItemCompleted')
    if (status === 'in_progress') return t('chat.todoItemRunning')
    if (status === 'cancelled') return t('chat.todoItemCancelled')
    return t('chat.todoItemPending')
  }
  if (status === 'completed') return t('chat.todoItemCompleted')
  if (status === 'cancelled') return t('chat.todoItemCancelled')
  if (status === 'in_progress') {
    if (runOutcome.value === 'cancelled' || overall.value === 'interrupted') return t('chat.todoItemInterrupted')
    if (runOutcome.value === 'failed' || overall.value === 'failed') return t('chat.todoItemFailed')
    return t('chat.todoItemInterrupted')
  }
  // pending after seal
  return t('chat.todoItemSkipped')
}

function itemVisualClass(status: TodoStatus): string {
  if (!sealed.value) return status
  if (status === 'completed' || status === 'cancelled') return status
  if (status === 'in_progress') {
    if (runOutcome.value === 'failed' || overall.value === 'failed') return 'failed'
    return 'interrupted'
  }
  return 'skipped'
}

function toggle() {
  collapsed.value = !collapsed.value
}
</script>

<template>
  <div
    class="todo"
    :class="[
      overall,
      {
        streaming: block.status === 'streaming' || live,
        collapsed,
      },
    ]"
  >
    <button type="button" class="todo-head" :aria-expanded="!collapsed" @click="toggle">
      <AppIcon class="todo-chev" name="chevron-right" :size="12" :stroke-width="2" />
      <AppIcon name="list" :size="14" :stroke-width="1.75" />
      <span class="todo-kicker">{{ t('chat.todoTitle') }}</span>
      <span class="todo-badge" :class="overall">{{ overallLabel }}</span>
      <span class="todo-count">{{ progressLabel }}</span>
      <span v-if="collapsed && summaryLine" class="todo-summary" :title="summaryLine">{{ summaryLine }}</span>
    </button>
    <div v-show="!collapsed" class="todo-body">
      <ol v-if="items.length" class="todo-list">
        <li v-for="item in items" :key="item.id" class="todo-item" :class="itemVisualClass(item.status)">
          <span class="todo-mark" :aria-label="itemStatusLabel(item.status)">
            <AppIcon v-if="item.status === 'completed'" name="check" :size="12" :stroke-width="2" />
            <AppIcon
              v-else-if="itemVisualClass(item.status) === 'interrupted' || itemVisualClass(item.status) === 'failed'"
              name="close"
              :size="12"
              :stroke-width="2"
            />
            <AppIcon v-else-if="item.status === 'cancelled' || itemVisualClass(item.status) === 'skipped'" name="minus" :size="12" :stroke-width="2" />
            <AppIcon v-else-if="item.status === 'in_progress'" name="loader" :size="12" :stroke-width="1.75" />
          </span>
          <span class="todo-text">{{ item.content }}</span>
          <span class="todo-item-status">{{ itemStatusLabel(item.status) }}</span>
        </li>
      </ol>
      <p v-else class="todo-empty">{{ t('chat.todoEmpty') }}</p>
    </div>
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
.todo.collapsed {
  padding-bottom: 8px;
}
.todo.completed {
  border-color: rgba(34, 197, 94, 0.35);
}
.todo.failed,
.todo.incomplete {
  border-color: rgba(239, 68, 68, 0.35);
}
.todo.interrupted {
  border-color: rgba(245, 158, 11, 0.45);
}
.todo.cancelled,
.todo.partial {
  border-color: color-mix(in srgb, var(--text-muted) 35%, var(--border));
}
.todo.in_progress,
.todo.streaming {
  border-color: color-mix(in srgb, var(--primary) 28%, var(--border));
}
.todo-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  text-align: left;
}
.todo:not(.collapsed) .todo-head {
  margin-bottom: 6px;
}
.todo-chev {
  flex-shrink: 0;
  transition: transform 0.15s ease;
}
.todo:not(.collapsed) .todo-chev {
  transform: rotate(90deg);
}
.todo-kicker {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.todo-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 650;
  line-height: 1.2;
  padding: 2px 6px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--text-muted);
  background: var(--code-bg);
}
.todo-badge.completed {
  color: #15803d;
  border-color: rgba(34, 197, 94, 0.35);
  background: rgba(34, 197, 94, 0.12);
}
.todo-badge.in_progress {
  color: var(--primary);
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  background: var(--primary-soft);
}
.todo-badge.failed,
.todo-badge.incomplete {
  color: #b91c1c;
  border-color: rgba(239, 68, 68, 0.35);
  background: rgba(239, 68, 68, 0.1);
}
.todo-badge.interrupted {
  color: #b45309;
  border-color: rgba(245, 158, 11, 0.45);
  background: rgba(245, 158, 11, 0.12);
}
.todo-badge.cancelled,
.todo-badge.partial {
  color: var(--text-secondary);
  background: var(--code-bg);
}
.todo-count {
  margin-left: auto;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.todo-summary {
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-secondary);
}
.todo-body {
  min-width: 0;
}
.todo-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--text);
}
.todo-item.completed .todo-text,
.todo-item.cancelled .todo-text,
.todo-item.skipped .todo-text,
.todo-item.interrupted .todo-text,
.todo-item.failed .todo-text {
  color: var(--text-muted);
}
.todo-item.completed .todo-text,
.todo-item.cancelled .todo-text,
.todo-item.skipped .todo-text {
  text-decoration: line-through;
}
.todo-item.in_progress .todo-text {
  color: var(--primary);
  font-weight: 550;
}
.todo-mark {
  width: 16px;
  height: 16px;
  margin-top: 1px;
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
  border-radius: 4px;
  border: 1.5px solid color-mix(in srgb, var(--text-muted) 45%, var(--border-strong));
  background-color: var(--panel-bg);
  color: var(--text-muted);
}
.todo-item.completed .todo-mark {
  color: #15803d;
  border-color: rgba(34, 197, 94, 0.35);
  background: rgba(34, 197, 94, 0.1);
}
.todo-item.in_progress .todo-mark {
  color: var(--primary);
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  background: var(--primary-soft);
}
.todo-item.interrupted .todo-mark {
  color: #b45309;
  border-color: rgba(245, 158, 11, 0.45);
  background: rgba(245, 158, 11, 0.12);
}
.todo-item.failed .todo-mark {
  color: #b91c1c;
  border-color: rgba(239, 68, 68, 0.35);
  background: rgba(239, 68, 68, 0.1);
}
.todo-item.cancelled .todo-mark,
.todo-item.skipped .todo-mark {
  color: var(--text-muted);
}
.todo-text {
  flex: 1;
  min-width: 0;
}
.todo-item-status {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 1px;
}
.todo-item.completed .todo-item-status {
  color: #15803d;
}
.todo-item.in_progress .todo-item-status {
  color: var(--primary);
}
.todo-item.interrupted .todo-item-status {
  color: #b45309;
}
.todo-item.failed .todo-item-status {
  color: #b91c1c;
}
.todo-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
