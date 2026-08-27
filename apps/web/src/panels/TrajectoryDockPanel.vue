<script setup lang="ts">
import TrajectoryPanel from '@/panels/TrajectoryPanel.vue'
</script>

<template>
  <div class="panel-shell trajectory-dock">
    <TrajectoryPanel />
  </div>
</template>

<style scoped>
.trajectory-dock {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
</style>
