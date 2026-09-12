<script setup lang="ts">
import { computed, useId } from 'vue'
import { useBrandMark, type BrandMarkId } from '@/utils/brandMark'

const props = withDefaults(
  defineProps<{
    size?: number
    variant?: BrandMarkId
  }>(),
  { size: 26 },
)

const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
const { brandMark } = useBrandMark()
const mark = computed(() => props.variant || brandMark.value)
const gradId = computed(() => `ca-brand-grad-${uid}`)
const fill = computed(() => `url(#${gradId.value})`)
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
      <linearGradient :id="gradId" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
        <stop stop-color="var(--brand-grad-a, #818cf8)" />
        <stop offset="1" stop-color="var(--brand-grad-b, #6366f1)" />
      </linearGradient>
    </defs>

    <g v-if="mark === 'atom'">
      <rect width="32" height="32" rx="8" :fill="fill" />
      <circle cx="16" cy="16" r="3.5" fill="white" fill-opacity="0.95" />
      <ellipse cx="16" cy="16" rx="10" ry="4" stroke="white" stroke-width="1.5" stroke-opacity="0.9" />
      <ellipse cx="16" cy="16" rx="10" ry="4" stroke="white" stroke-width="1.5" stroke-opacity="0.9" transform="rotate(60 16 16)" />
      <ellipse cx="16" cy="16" rx="10" ry="4" stroke="white" stroke-width="1.5" stroke-opacity="0.9" transform="rotate(120 16 16)" />
    </g>

    <g v-else-if="mark === 'ca'">
      <rect width="32" height="32" rx="8" :fill="fill" />
      <path
        d="M18.6 9.4a7.2 7.2 0 1 0 0 13.2"
        stroke="white"
        stroke-width="2.35"
        stroke-linecap="round"
      />
      <path
        d="M16.6 22.4 21.4 9.8 26.2 22.4"
        stroke="white"
        stroke-width="2.35"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path d="M18.5 17.2h5.8" stroke="white" stroke-width="2.1" stroke-linecap="round" />
    </g>

    <g v-else-if="mark === 'brackets'">
      <rect width="32" height="32" rx="8" :fill="fill" />
      <path
        d="M11.5 8.5 6.2 16l5.3 7.5"
        stroke="white"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path
        d="M20.5 8.5 25.8 16l-5.3 7.5"
        stroke="white"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <ellipse cx="16" cy="16" rx="5.4" ry="2.15" stroke="white" stroke-width="1.15" stroke-opacity="0.9" />
      <ellipse
        cx="16"
        cy="16"
        rx="5.4"
        ry="2.15"
        stroke="white"
        stroke-width="1.15"
        stroke-opacity="0.9"
        transform="rotate(75 16 16)"
      />
      <circle cx="16" cy="16" r="2.15" fill="white" />
    </g>

    <g v-else-if="mark === 'cursor'">
      <rect width="32" height="32" rx="8" :fill="fill" />
      <path
        d="M10.4 7.6 10.4 23.6 14.6 19.4 18 26.4 20.5 25.3 16.9 18.1 22.6 18.1Z"
        fill="white"
      />
      <path
        d="M24.2 6.4 25.05 8.5 27.2 9.35 25.05 10.2 24.2 12.3 23.35 10.2 21.2 9.35 23.35 8.5Z"
        fill="white"
        fill-opacity="0.95"
      />
    </g>

    <g v-else-if="mark === 'hex'">
      <path
        d="M16 2.2 28.1 9.2v13.6L16 29.8 3.9 22.8V9.2Z"
        :fill="fill"
      />
      <circle cx="16" cy="16" r="3.1" fill="white" fill-opacity="0.95" />
      <ellipse cx="16" cy="16" rx="8.6" ry="3.4" stroke="white" stroke-width="1.45" stroke-opacity="0.92" />
      <ellipse
        cx="16"
        cy="16"
        rx="8.6"
        ry="3.4"
        stroke="white"
        stroke-width="1.45"
        stroke-opacity="0.92"
        transform="rotate(70 16 16)"
      />
    </g>
  </svg>
</template>

<style scoped>
.brand-logo {
  display: block;
  flex-shrink: 0;
}
</style>
