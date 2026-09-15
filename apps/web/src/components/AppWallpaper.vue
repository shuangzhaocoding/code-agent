<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  currentWallpaper,
  currentWallpaperImage,
  type WallpaperId,
} from '@/utils/desktopDecor'

const id = ref<WallpaperId>(currentWallpaper())
const image = ref(currentWallpaperImage())

const show = computed(() => {
  if (id.value === 'none') return false
  if (id.value === 'custom') return Boolean(image.value)
  return true
})

function onChange(e: Event) {
  const detail = (e as CustomEvent<{ id: WallpaperId; image: string }>).detail
  if (detail && typeof detail === 'object' && 'id' in detail) {
    id.value = detail.id
    image.value = detail.image || ''
    return
  }
  // backward compat if something still sends a bare string
  id.value = e as unknown as WallpaperId
}

onMounted(() => {
  id.value = currentWallpaper()
  image.value = currentWallpaperImage()
  window.addEventListener('ca-wallpaper', onChange as EventListener)
})
onUnmounted(() => {
  window.removeEventListener('ca-wallpaper', onChange as EventListener)
})
</script>

<template>
  <div
    v-if="show"
    class="wallpaper"
    :class="id === 'custom' ? 'wp-custom' : `wp-${id}`"
    aria-hidden="true"
  >
    <div
      v-if="id === 'custom'"
      class="wp-photo"
      :style="{ backgroundImage: `url(${image})` }"
    />
    <template v-else>
      <div class="wp-layer wp-base" />
      <div class="wp-layer wp-glow" />
    </template>
    <div class="wp-scrim" />
  </div>
</template>

<style scoped>
.wallpaper {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}
.wp-layer,
.wp-photo,
.wp-scrim {
  position: absolute;
  inset: 0;
}
.wp-photo {
  background-position: center;
  background-size: cover;
  background-repeat: no-repeat;
}

/* Minimal veil — panels carry the glass; don't wash out the photo. */
.wp-scrim {
  background: color-mix(in srgb, var(--surface) 6%, transparent);
}
.wp-custom .wp-scrim {
  background: color-mix(in srgb, var(--surface) 4%, transparent);
}

.wp-aurora .wp-base {
  background: linear-gradient(145deg, #07161a 0%, #0d2c33 42%, #123a45 100%);
}
.wp-aurora .wp-glow {
  background:
    radial-gradient(ellipse 70% 50% at 18% 12%, rgba(45, 212, 166, 0.35), transparent 60%),
    radial-gradient(ellipse 55% 45% at 88% 28%, rgba(56, 152, 189, 0.28), transparent 62%),
    radial-gradient(ellipse 60% 40% at 50% 100%, rgba(15, 80, 90, 0.45), transparent 70%);
}

.wp-dusk .wp-base {
  background: linear-gradient(155deg, #140e10 0%, #2a1614 48%, #1a1218 100%);
}
.wp-dusk .wp-glow {
  background:
    radial-gradient(ellipse 65% 45% at 78% 8%, rgba(251, 146, 60, 0.38), transparent 58%),
    radial-gradient(ellipse 50% 50% at 12% 80%, rgba(147, 51, 120, 0.22), transparent 65%),
    radial-gradient(circle at 82% 16%, rgba(255, 220, 170, 0.45) 0 1.5px, transparent 2.5px);
}

.wp-harbor .wp-base {
  background: linear-gradient(180deg, #d9e4ef 0%, #a8bdd2 52%, #5f7f9c 100%);
}
.wp-harbor .wp-glow {
  background:
    radial-gradient(ellipse 80% 40% at 50% -5%, rgba(255, 255, 255, 0.7), transparent 70%),
    linear-gradient(180deg, transparent 60%, rgba(20, 45, 70, 0.2) 100%);
}

html[data-theme='dark'] .wp-harbor .wp-base {
  background: linear-gradient(180deg, #121820 0%, #1a2836 50%, #0e1824 100%);
}
html[data-theme='dark'] .wp-harbor .wp-glow {
  background:
    radial-gradient(ellipse 80% 40% at 50% -5%, rgba(140, 175, 210, 0.14), transparent 70%),
    linear-gradient(180deg, transparent 55%, rgba(8, 16, 28, 0.35) 100%);
}
</style>
