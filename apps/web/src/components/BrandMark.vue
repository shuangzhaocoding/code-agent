<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 26 })
</script>

<template>
  <svg
    class="brand-logo"
    :width="size"
    :height="size"
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <defs>
      <linearGradient id="ca-brand-grad" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
        <stop stop-color="var(--brand-grad-a, #818cf8)" />
        <stop offset="1" stop-color="var(--brand-grad-b, #6366f1)" />
      </linearGradient>
    </defs>
    <rect width="32" height="32" rx="8" fill="url(#ca-brand-grad)" />
    <circle cx="16" cy="16" r="3.5" fill="white" fill-opacity="0.95" />
    <ellipse cx="16" cy="16" rx="10" ry="4" stroke="white" stroke-width="1.5" stroke-opacity="0.9" />
    <ellipse cx="16" cy="16" rx="10" ry="4" stroke="white" stroke-width="1.5" stroke-opacity="0.9" transform="rotate(60 16 16)" />
    <ellipse cx="16" cy="16" rx="10" ry="4" stroke="white" stroke-width="1.5" stroke-opacity="0.9" transform="rotate(120 16 16)" />
  </svg>
</template>

<style scoped>
.brand-logo {
  display: block;
  flex-shrink: 0;
}
</style>
