<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, toRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { scrollToBottom } from '@/utils/smoothScroll'
import { useAppStore } from '@/stores/app'
import { api } from '@/api/http'
import AppIcon from '@/components/AppIcon.vue'
import TrajectoryOverview from '@/components/TrajectoryOverview.vue'
import { rendererFor } from '@/renderers'
import type { Block } from '@/protocol/applyEvent'
import { useThrottledTrajectory } from '@/composables/useThrottledTrajectory'
import {
  TRAJECTORY_FILTERS,
  type TrajectoryEntry,
  type TrajectoryKind,
} from '@/utils/trajectory'
import { formatRelativeTime } from '@/utils/relativeTime'

type ActiveRun = {
  run_id: string
  status: string
  mode: string
  started_at?: string | null
  conversation_id: string
  conversation_title?: string | null
}

const { t } = useI18n()
const store = useAppStore()
const filter = ref<'all' | TrajectoryKind>('all')
const expanded = ref<string | null>(null)
const activeId = ref<string | null>(null)
const scroller = ref<HTMLElement | null>(null)
const followTail = ref(true)
const activeRuns = ref<ActiveRun[]>([])
const cancellingId = ref<string | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const { entries, timelineSpans } = useThrottledTrajectory(toRef(store, 'messages'))

const filtered = computed(() => {
  if (filter.value === 'all') return entries.value
  return entries.value.filter((e) => e.kind === filter.value)
})

const grouped = computed(() => {
  const map = new Map<number, TrajectoryEntry[]>()
  for (const entry of filtered.value) {
    const list = map.get(entry.turn) || []
    list.push(entry)
    map.set(entry.turn, list)
  }
  return [...map.entries()].sort((a, b) => a[0] - b[0])
})

const counts = computed(() => {
  const out: Record<string, number> = { all: entries.value.length }
  for (const entry of entries.value) {
    out[entry.kind] = (out[entry.kind] || 0) + 1
  }
  return out
})

async function loadActiveRuns() {
  const wid = store.workspaceId
  if (!wid) {
    activeRuns.value = []
    return
  }
  try {
    const data = await api<{ runs: ActiveRun[] }>(`/api/runs/active?workspace_id=${encodeURIComponent(wid)}`)
    activeRuns.value = data.runs || []
  } catch {
    /* ignore poll errors */
  }
}

async function openRun(row: ActiveRun) {
  if (row.conversation_id !== store.conversationId) {
    await store.openConversation(row.conversation_id)
  }
}

async function cancelRun(row: ActiveRun) {
  if (cancellingId.value) return
  cancellingId.value = row.run_id
  try {
    await api(`/api/runs/${row.run_id}/cancel`, { method: 'POST' })
    await loadActiveRuns()
  } finally {
    cancellingId.value = null
  }
}

function toggle(entry: TrajectoryEntry) {
  expanded.value = expanded.value === entry.id ? null : entry.id
  activeId.value = entry.id
}

async function focusEntry(entryId: string) {
  activeId.value = entryId
  expanded.value = entryId
  await nextTick()
  const el = scroller.value?.querySelector(`[data-entry-id="${entryId}"]`)
  el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
}

function onScroll() {
  const el = scroller.value
  if (!el) return
  const dist = el.scrollHeight - el.scrollTop - el.clientHeight
  followTail.value = dist < 80
}

async function scrollToTail(force = false) {
  if (!force && !followTail.value) return
  await nextTick()
  const el = scroller.value
  if (el) scrollToBottom(el, force ? 'smooth' : 'auto')
}

watch(
  () => [entries.value.length, entries.value.at(-1)?.block.status],
  () => scrollToTail(),
)

watch(filter, () => scrollToTail(true))

watch(
  () => [store.workspaceId, store.runStatus, store.conversationId] as const,
  () => void loadActiveRuns(),
)

onMounted(() => {
  void loadActiveRuns()
  pollTimer = setInterval(() => void loadActiveRuns(), 4000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="trajectory-panel">
    <header class="trajectory-head">
      <div class="trajectory-title">
        <AppIcon name="clock" :size="15" />
        <span>{{ t('trajectory.title') }}</span>
        <em v-if="entries.length" class="trajectory-count">{{ entries.length }}</em>
      </div>
    </header>

    <section v-if="activeRuns.length" class="active-runs">
      <div class="active-head">
        <AppIcon name="zap" :size="14" />
        <strong>{{ t('trajectory.activeRuns', { n: activeRuns.length }) }}</strong>
        <span class="active-hint">{{ t('trajectory.activeHint') }}</span>
      </div>
      <button
        v-for="row in activeRuns"
        :key="row.run_id"
        type="button"
        class="active-row"
        :class="{ current: row.conversation_id === store.conversationId }"
        @click="openRun(row)"
      >
        <span class="active-dot" :data-status="row.status" />
        <span class="active-copy">
          <strong>{{ row.conversation_title || t('trajectory.untitled') }}</strong>
          <small>
            {{ row.status }} · {{ row.mode }}
            <template v-if="row.started_at"> · {{ formatRelativeTime(row.started_at) }}</template>
          </small>
        </span>
        <button
          type="button"
          class="active-cancel"
          :disabled="cancellingId === row.run_id"
          :title="t('common.stop')"
          @click.stop="cancelRun(row)"
        >
          <AppIcon name="close" :size="14" />
        </button>
      </button>
    </section>

    <TrajectoryOverview
      v-if="timelineSpans.length"
      :spans="timelineSpans"
      :active-id="activeId"
      @select="focusEntry"
    />

    <div class="trajectory-filters" role="tablist" :aria-label="t('trajectory.filter')">
      <button
        v-for="item in TRAJECTORY_FILTERS"
        :key="item.id"
        type="button"
        class="filter-chip"
        :class="{ active: filter === item.id, disabled: item.id !== 'all' && !counts[item.id] }"
        :disabled="item.id !== 'all' && !counts[item.id]"
        @click="filter = item.id"
      >
        {{ item.label }}
        <span v-if="counts[item.id]" class="filter-num">{{ counts[item.id] }}</span>
      </button>
    </div>

    <div ref="scroller" class="trajectory-ledger" @scroll="onScroll">
      <p v-if="!entries.length" class="trajectory-empty">
        {{ t('trajectory.empty') }}
      </p>

      <section v-for="[turn, turnEntries] in grouped" :key="turn" class="turn-group">
        <div class="turn-rule">
          <span>Turn {{ turn }}</span>
        </div>
        <article
          v-for="entry in turnEntries"
          :key="entry.id"
          :data-entry-id="entry.id"
          class="ledger-row"
          :class="[entry.kind, entry.block.status, { open: expanded === entry.id, active: activeId === entry.id }]"
        >
          <button type="button" class="ledger-head" @click="toggle(entry)">
            <span class="ledger-dot" aria-hidden="true" />
            <span class="ledger-copy">
              <span class="ledger-label">
                {{ entry.label }}
                <i v-if="entry.block.status === 'streaming'" class="ledger-live">{{ t('trajectory.running') }}</i>
                <i v-else-if="entry.block.status === 'error'" class="ledger-live error">{{ t('trajectory.failed') }}</i>
              </span>
              <span v-if="entry.subtitle" class="ledger-sub">{{ entry.subtitle }}</span>
            </span>
            <AppIcon class="ledger-chev" name="chevron" :size="16" :stroke-width="1.75" />
          </button>
          <div v-if="expanded === entry.id" class="ledger-body">
            <component :is="rendererFor(entry.block.type)" :block="entry.block as Block" />
          </div>
        </article>
      </section>
    </div>
  </div>
</template>

<style scoped>
.trajectory-panel {
  height: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--panel-bg);
}
.trajectory-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 44px;
  padding: 0 12px;
  border-bottom: var(--border-width) solid var(--border);
  flex-shrink: 0;
}
.trajectory-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
}
.trajectory-count {
  font-style: normal;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  background: var(--code-bg);
  padding: 1px 6px;
  border-radius: 999px;
}
.active-runs {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-bottom: var(--border-width) solid var(--border);
  flex-shrink: 0;
  background: color-mix(in srgb, var(--primary-soft, #f59e0b22) 40%, transparent);
}
.active-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.active-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
}
.active-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-bg);
  color: inherit;
  padding: 8px 8px 8px 10px;
  cursor: pointer;
  text-align: left;
}
.active-row.current {
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
}
.active-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
}
.active-dot[data-status='queued'] {
  background: var(--text-muted);
}
.active-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.active-copy strong {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.active-copy small {
  font-size: 11px;
  color: var(--text-muted);
}
.active-cancel {
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
}
.active-cancel:hover {
  color: var(--danger, #f87171);
  background: color-mix(in srgb, var(--danger, #f87171) 12%, transparent);
}
.trajectory-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 12px;
  border-bottom: var(--border-width) solid var(--border);
  flex-shrink: 0;
}
.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 8px;
  border: var(--border-width) solid var(--border);
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.filter-chip:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--primary) 30%, var(--border));
  color: var(--text-h);
}
.filter-chip.active {
  background: var(--primary-soft);
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  color: var(--primary);
}
.filter-chip.disabled,
.filter-chip:disabled {
  opacity: 0.45;
  cursor: default;
}
.filter-num {
  font-size: 10px;
  opacity: 0.85;
}
.trajectory-ledger {
  flex: 1;
  min-height: 0;
  overflow: auto;
  scroll-behavior: smooth;
  padding: 8px 10px 16px;
}
.trajectory-empty {
  margin: 24px 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-muted);
  text-align: center;
}
.turn-group + .turn-group {
  margin-top: 8px;
}
.turn-rule {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0 6px;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.turn-rule::before,
.turn-rule::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}
.ledger-row {
  border-radius: var(--radius-sm);
  overflow: hidden;
  margin-bottom: 4px;
}
.ledger-row.active .ledger-head {
  background: color-mix(in srgb, var(--primary-soft) 70%, var(--code-bg));
}
.ledger-head {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 8px 8px 6px;
  border: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.ledger-row:hover .ledger-head {
  background: var(--code-bg);
}
.ledger-row.open .ledger-head {
  background: color-mix(in srgb, var(--code-bg) 70%, var(--panel-bg));
}
.ledger-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
  background: var(--text-muted);
}
.ledger-row.tool .ledger-dot { background: var(--traj-tool); }
.ledger-row.think .ledger-dot { background: var(--traj-think); }
.ledger-row.context .ledger-dot { background: var(--traj-context); }
.ledger-row.diff .ledger-dot { background: var(--primary); }
.ledger-row.terminal .ledger-dot { background: #64748b; }
.ledger-row.error .ledger-dot { background: var(--danger); }
.ledger-copy {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ledger-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.ledger-live {
  font-style: normal;
  font-size: 10px;
  font-weight: 600;
  color: var(--primary);
}
.ledger-live.error { color: var(--danger); }
.ledger-sub {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ledger-chev {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--text-muted);
  transform: rotate(-90deg);
  transition: transform 0.15s ease;
}
.ledger-row.open .ledger-chev {
  transform: rotate(0deg);
}
.ledger-body {
  padding: 0 8px 10px 22px;
}
.ledger-body :deep(.card) {
  margin: 0;
}
</style>
