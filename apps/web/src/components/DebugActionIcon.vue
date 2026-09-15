<script setup lang="ts">
withDefaults(
  defineProps<{
    kind: 'start' | 'restart'
    size?: number | string
  }>(),
  { size: 16 },
)
</script>

<template>
  <!-- Start debugging: solid green beetle -->
  <svg
    v-if="kind === 'start'"
    class="debug-action-icon debug-action-icon--start"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
    :width="size"
    :height="size"
  >
    <path
      d="M9.25 5.6 7.6 3.7M14.75 5.6l1.65-1.9"
      stroke="currentColor"
      stroke-width="1.7"
      stroke-linecap="round"
    />
    <path
      d="M8.2 8.1a3.8 3.8 0 0 1 7.6 0v1.35a3.8 3.8 0 0 1-7.6 0V8.1Z"
      fill="currentColor"
    />
    <path
      d="M12 12.2v6.6M7.6 14H5.4M16.4 14h2.2M7.6 17.2H6M16.4 17.2H18"
      stroke="currentColor"
      stroke-width="1.7"
      stroke-linecap="round"
    />
    <path
      d="M7.35 10.1c-1.15.45-1.95 1.35-1.95 2.55M16.65 10.1c1.15.45 1.95 1.35 1.95 2.55"
      stroke="currentColor"
      stroke-width="1.55"
      stroke-linecap="round"
    />
  </svg>

  <!-- Restart: counter-clockwise arrow with green bug at the base -->
  <svg
    v-else
    class="debug-action-icon debug-action-icon--restart"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
    :width="size"
    :height="size"
  >
    <path
      d="M5 11.5A7 7 0 1 0 7.1 6.4"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
    />
    <path
      d="M5 3.8v4.8h4.8"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <g class="restart-bug">
      <ellipse cx="12" cy="15.35" rx="2.35" ry="2.55" fill="currentColor" />
      <path
        d="M12 17.6v2.15M9.7 18.35H8.35M14.3 18.35h1.35M9.95 19.85H8.9M14.05 19.85h1.05M10.55 13.55 9.7 12.55M13.45 13.55l.85-1"
        stroke="currentColor"
        stroke-width="1.15"
        stroke-linecap="round"
      />
    </g>
  </svg>
</template>

<style scoped>
.debug-action-icon {
  display: block;
  flex-shrink: 0;
}
.debug-action-icon--start {
  color: #89d185;
}
.debug-action-icon--restart {
  color: color-mix(in srgb, var(--text-h, #e8e8e8) 92%, transparent);
}
.debug-action-icon--restart .restart-bug {
  color: #89d185;
}
</style>
