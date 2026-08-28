<script setup lang="ts">
import { computed, nextTick, ref, toRef, watch } from 'vue'
import { scrollToBottom } from '@/utils/smoothScroll'
import { useAppStore } from '@/stores/app'
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

const store = useAppStore()
const filter = ref<'all' | TrajectoryKind>('all')
const expanded = ref<string | null>(null)
const activeId = ref<string | null>(null)
const scroller = ref<HTMLElement | null>(null)
const followTail = ref(true)

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
</script>

<template>
  <div class="trajectory-panel">
    <header class="trajectory-head">
      <div class="trajectory-title">
        <AppIcon name="clock" :size="15" />
        <span>轨迹</span>
        <em v-if="entries.length" class="trajectory-count">{{ entries.length }}</em>
      </div>
    </header>

    <TrajectoryOverview
      v-if="timelineSpans.length"
      :spans="timelineSpans"
      :active-id="activeId"
      @select="focusEntry"
    />

    <div class="trajectory-filters" role="tablist" aria-label="轨迹筛选">
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
        Agent 运行后，工具调用、思考过程与上下文注入会显示在这里。
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
                <i v-if="entry.block.status === 'streaming'" class="ledger-live">进行中</i>
                <i v-else-if="entry.block.status === 'error'" class="ledger-live error">失败</i>
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
