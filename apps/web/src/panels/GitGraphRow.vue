<script setup lang="ts">
import { computed } from 'vue'
import { laneColor, type GraphRow } from '@/utils/gitGraph'

const props = defineProps<{ row: GraphRow }>()

const COL = 12
const PAD = 8
const H = 40
const R = 3.5

function x(lane: number) {
  return PAD + lane * COL
}

const width = computed(() => Math.max(PAD * 2 + 4, PAD * 2 + props.row.maxLane * COL))
const mid = H / 2
const color = computed(() => laneColor(props.row.lane))
const pass = computed(() => props.row.through.filter((lane) => lane !== props.row.lane))
</script>

<template>
  <svg class="graph" :width="width" :height="H" aria-hidden="true">
    <line
      v-for="lane in pass"
      :key="'p' + lane"
      :x1="x(lane)"
      y1="0"
      :x2="x(lane)"
      :y2="H"
      :stroke="laneColor(lane)"
      stroke-width="1.5"
    />
    <line
      :x1="x(row.lane)"
      y1="0"
      :x2="x(row.lane)"
      :y2="mid - R"
      :stroke="color"
      stroke-width="1.5"
    />
    <path
      v-for="(line, index) in row.lines"
      :key="'e' + index"
      :d="line.from === line.to
        ? `M ${x(line.from)} ${mid + R} L ${x(line.to)} ${H}`
        : `M ${x(line.from)} ${mid} C ${x(line.from)} ${H - 2}, ${x(line.to)} ${2}, ${x(line.to)} ${H}`"
      :stroke="laneColor(line.to)"
      fill="none"
      stroke-width="1.5"
    />
    <circle
      :cx="x(row.lane)"
      :cy="mid"
      :r="R"
      :fill="row.is_head ? color : 'var(--panel-bg)'"
      :stroke="color"
      stroke-width="1.75"
    />
  </svg>
</template>

<style scoped>
.graph {
  display: block;
  flex-shrink: 0;
}
</style>
