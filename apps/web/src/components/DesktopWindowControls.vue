<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getDesktopBridge, needsDesktopWindowControls } from '@/utils/desktop'

const { t } = useI18n()
const maximized = ref(false)
const show = ref(needsDesktopWindowControls())

async function refreshMaximized() {
  const desktop = getDesktopBridge()
  if (!desktop?.isMaximized) return
  try {
    maximized.value = Boolean(await desktop.isMaximized())
  } catch {
    maximized.value = false
  }
}

function onState(e: Event) {
  const detail = (e as CustomEvent<{ maximized?: boolean }>).detail
  if (typeof detail?.maximized === 'boolean') maximized.value = detail.maximized
}

onMounted(() => {
  show.value = needsDesktopWindowControls()
  void refreshMaximized()
  window.addEventListener('ca-desktop-window-state', onState as EventListener)
})
onUnmounted(() => {
  window.removeEventListener('ca-desktop-window-state', onState as EventListener)
})

function minimize() {
  void getDesktopBridge()?.windowMinimize?.()
}
function toggleMaximize() {
  void getDesktopBridge()?.windowMaximizeToggle?.()
}
function close() {
  void getDesktopBridge()?.windowClose?.()
}
</script>

<template>
  <div v-if="show" class="win-controls" role="group" :aria-label="t('desktop.windowControls')">
    <button type="button" class="win-btn" :title="t('desktop.minimize')" @click="minimize">
      <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
        <path d="M2 6h8" fill="none" stroke="currentColor" stroke-width="1.2" />
      </svg>
    </button>
    <button
      type="button"
      class="win-btn"
      :title="maximized ? t('desktop.restore') : t('desktop.maximize')"
      @click="toggleMaximize"
    >
      <svg v-if="!maximized" viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
        <rect x="2.25" y="2.25" width="7.5" height="7.5" fill="none" stroke="currentColor" stroke-width="1.2" />
      </svg>
      <svg v-else viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
        <path
          d="M3.5 4.25h4.25V8.5H3.5V4.25zm1.75-1.5h4.25V7"
          fill="none"
          stroke="currentColor"
          stroke-width="1.2"
        />
      </svg>
    </button>
    <button type="button" class="win-btn win-btn-close" :title="t('desktop.close')" @click="close">
      <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
        <path d="M3 3l6 6M9 3L3 9" fill="none" stroke="currentColor" stroke-width="1.2" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.win-controls {
  display: flex;
  align-items: stretch;
  flex-shrink: 0;
  align-self: stretch;
  height: var(--desktop-titlebar-height, 38px);
  margin-left: auto;
  z-index: 5;
  -webkit-app-region: no-drag;
}
.win-btn {
  width: 46px;
  height: 100%;
  border: 0;
  background: transparent;
  color: var(--text-h);
  display: grid;
  place-items: center;
  cursor: pointer;
  padding: 0;
}
.win-btn:hover {
  background: color-mix(in srgb, var(--text-h) 8%, transparent);
}
.win-btn-close:hover {
  background: #e81123;
  color: #fff;
}
</style>
