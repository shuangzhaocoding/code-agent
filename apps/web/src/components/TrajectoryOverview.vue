<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TimelineSpan, TrajectoryKind } from '@/utils/trajectory'

const props = defineProps<{
  spans: TimelineSpan[]
  activeId?: string | null
}>()

const emit = defineEmits<{ select: [entryId: string] }>()

const track = ref<HTMLElement | null>(null)

const turnMarkers = computed(() => {
  const turns = new Map<number, number>()
  for (const span of props.spans) {
    if (!turns.has(span.turn)) turns.set(span.turn, span.left)
  }
  return [...turns.entries()].sort((a, b) => a[0] - b[0])
})

function kindClass(kind: TrajectoryKind) {
  return kind
}

function onSelect(span: TimelineSpan) {
  emit('select', span.entryId)
}
</script>

<template>
  <div class="timeline-overview">
    <div class="timeline-head">
      <span class="timeline-label">时间轴</span>
      <span class="timeline-meta">{{ spans.length }} 事件</span>
    </div>
    <div ref="track" class="timeline-track" role="list" aria-label="运行时间轴">
      <div
        v-for="[turn, left] in turnMarkers"
        :key="turn"
        class="turn-marker"
        :style="{ left: `${left}%` }"
      >
        T{{ turn }}
      </div>
      <button
        v-for="span in spans"
        :key="span.id"
        type="button"
        class="timeline-span"
        :class="[kindClass(span.kind), { active: activeId === span.entryId, streaming: span.streaming }]"
        :style="{ left: `${span.left}%`, width: `${span.width}%` }"
        :title="`${span.label}${span.streaming ? ' · 进行中' : ''}`"
        @click="onSelect(span)"
      />
    </div>
    <div class="timeline-legend">
      <span><i class="dot tool" />工具</span>
      <span><i class="dot think" />思考</span>
      <span><i class="dot context" />上下文</span>
      <span><i class="dot diff" />变更</span>
    </div>
  </div>
</template>

<style scoped>
.timeline-overview {
  padding: 10px 12px 8px;
  border-bottom: var(--border-width) solid var(--border);
  flex-shrink: 0;
  background: color-mix(in srgb, var(--code-bg) 35%, var(--panel-bg));
}
.timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.timeline-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.timeline-meta {
  font-size: 10px;
  color: var(--text-muted);
}
.timeline-track {
  position: relative;
  height: 28px;
  border-radius: 6px;
  background: var(--code-bg);
  overflow: hidden;
}
.turn-marker {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: color-mix(in srgb, var(--border) 80%, transparent);
  font-size: 9px;
  color: var(--text-muted);
  padding-top: 2px;
  padding-left: 3px;
  pointer-events: none;
}
.timeline-span {
  position: absolute;
  top: 5px;
  height: 18px;
  min-width: 3px;
  border: 0;
  border-radius: 3px;
  padding: 0;
  cursor: pointer;
  opacity: 0.92;
  transition: transform 0.12s ease, opacity 0.12s ease;
}
.timeline-span:hover {
  transform: translateY(-1px);
  opacity: 1;
  z-index: 2;
}
.timeline-span.active {
  outline: 2px solid var(--primary);
  outline-offset: 1px;
  z-index: 3;
}
.timeline-span.streaming {
  animation: pulse-span 1.2s ease-in-out infinite;
}
.timeline-span.tool { background: var(--traj-tool); }
.timeline-span.think { background: var(--traj-think); }
.timeline-span.context { background: var(--traj-context); }
.timeline-span.diff { background: var(--primary); }
.timeline-span.terminal { background: #64748b; }
.timeline-span.error { background: var(--danger); }
.timeline-span.assistant,
.timeline-span.user,
.timeline-span.other { background: var(--text-muted); }
.timeline-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 8px;
  font-size: 10px;
  color: var(--text-muted);
}
.timeline-legend span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  display: inline-block;
}
.dot.tool { background: var(--traj-tool); }
.dot.think { background: var(--traj-think); }
.dot.context { background: var(--traj-context); }
.dot.diff { background: var(--primary); }
@keyframes pulse-span {
  0%, 100% { opacity: 0.65; }
  50% { opacity: 1; }
}
</style>
