<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import {
  currentPet,
  getPetPosition,
  pickCustomPetImage,
  resolvePetTaskStatus,
  setPet,
  setPetPosition,
  useDesktopDecor,
  type PetId,
} from '@/utils/desktopDecor'

const { t } = useI18n()
const store = useAppStore()
const { activeCustomPetId, activeCustomPet } = useDesktopDecor()

const petId = ref<PetId>(currentPet())
const hovering = ref(false)
const pos = ref(getPetPosition())
const dragging = ref(false)

let startX = 0
let startY = 0
let originX = 0
let originY = 0
let hideTimer: ReturnType<typeof setTimeout> | null = null

const visible = computed(() => petId.value !== 'none')
const showTip = computed(() => hovering.value && !dragging.value)

const taskStatus = computed(() =>
  resolvePetTaskStatus({
    runStatus: store.runStatus,
    isBusy: store.isRunBusy(),
    awaitingApproval: store.pendingApprovals.length > 0,
  }),
)

const activeCustomImage = computed(() => {
  if (petId.value !== 'custom') return null
  return pickCustomPetImage(taskStatus.value, activeCustomPet())
})

const tipLines = computed(() => {
  const workspace = store.workspace?.name || t('desktopDecor.tip.noWorkspace')
  const session = store.conversations.find((c) => c.id === store.conversationId)?.title
    || t('desktopDecor.tip.noSession')
  const model = store.modelId || t('desktopDecor.tip.noModel')
  const status = t(`desktopDecor.petStatuses.${taskStatus.value}`)
  const now = new Date()
  const time = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  return [
    { label: t('desktopDecor.tip.workspace'), value: workspace },
    { label: t('desktopDecor.tip.session'), value: session },
    { label: t('desktopDecor.tip.model'), value: model },
    { label: t('desktopDecor.tip.status'), value: status },
    { label: t('desktopDecor.tip.time'), value: time },
    {
      label: t('desktopDecor.tip.messages'),
      value: String(store.messages.length),
    },
  ]
})

const petTitle = computed(() => {
  if (petId.value === 'custom') {
    const name = activeCustomPet()?.name || t('desktopDecor.pets.custom')
    return `${name} · ${t(`desktopDecor.petStatuses.${taskStatus.value}`)}`
  }
  return t(`desktopDecor.pets.${petId.value}`)
})

/** Prefer side/edge with more room so the tip stays on-screen. */
const tipPlace = computed(() => {
  const tipH = 260
  const tipW = 280
  const petSize = 72
  const x = pos.value.x
  const y = pos.value.y
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1280
  const vh = typeof window !== 'undefined' ? window.innerHeight : 800
  const spaceAbove = y
  const spaceBelow = vh - (y + petSize)
  const spaceRight = vw - (x + petSize)
  const spaceLeft = x
  return {
    below: spaceAbove < tipH && spaceBelow >= Math.min(tipH, spaceAbove + 1),
    flip: spaceRight < tipW && spaceLeft > spaceRight,
  }
})

function clearHideTimer() {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
}

function onPetChange(e: Event) {
  const detail = (e as CustomEvent<{ id: PetId } | PetId>).detail
  const id = detail && typeof detail === 'object' && 'id' in detail ? detail.id : (detail as PetId)
  petId.value = id
  if (petId.value === 'none') hovering.value = false
}

function clampPos(x: number, y: number) {
  const maxX = Math.max(8, window.innerWidth - 88)
  const maxY = Math.max(8, window.innerHeight - 88)
  return {
    x: Math.min(maxX, Math.max(8, x)),
    y: Math.min(maxY, Math.max(8, y)),
  }
}

function onEnter() {
  clearHideTimer()
  hovering.value = true
}

function onLeave() {
  clearHideTimer()
  hideTimer = setTimeout(() => {
    hovering.value = false
    hideTimer = null
  }, 160)
}

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  const target = e.target as HTMLElement | null
  if (target?.closest('.pet-dismiss')) return
  const el = e.currentTarget as HTMLElement
  el.setPointerCapture(e.pointerId)
  dragging.value = true
  startX = e.clientX
  startY = e.clientY
  originX = pos.value.x
  originY = pos.value.y
}

function onPointerMove(e: PointerEvent) {
  if (!dragging.value) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  pos.value = clampPos(originX + dx, originY + dy)
}

function onPointerUp(e: PointerEvent) {
  if (!dragging.value) return
  dragging.value = false
  try {
    ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
  } catch {
    /* ignore */
  }
  setPetPosition(pos.value)
}

function dismissPet(e: Event) {
  e.preventDefault()
  e.stopPropagation()
  hovering.value = false
  setPet('none')
  petId.value = 'none'
}

function onResize() {
  pos.value = clampPos(pos.value.x, pos.value.y)
}

onMounted(() => {
  petId.value = currentPet()
  pos.value = clampPos(getPetPosition().x, getPetPosition().y)
  window.addEventListener('ca-pet', onPetChange as EventListener)
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  clearHideTimer()
  window.removeEventListener('ca-pet', onPetChange as EventListener)
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <div
    v-if="visible"
    class="pet-root"
    :class="{ tip: showTip }"
    :style="{ left: `${pos.x}px`, top: `${pos.y}px` }"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
  >
    <div
      class="pet"
      :class="[`pet-${petId}`, { dragging, open: showTip, custom: petId === 'custom' }]"
      role="button"
      tabindex="0"
      :title="petTitle"
      :aria-label="petTitle"
      :aria-expanded="showTip"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <button
        type="button"
        class="pet-dismiss"
        :title="t('desktopDecor.tip.dismiss')"
        :aria-label="t('desktopDecor.tip.dismiss')"
        @pointerdown.stop
        @click="dismissPet"
      >
        ×
      </button>

      <img
        v-if="petId === 'custom' && activeCustomImage"
        :key="`${activeCustomPetId}-${taskStatus}-${activeCustomImage.url}`"
        class="pet-img"
        :src="activeCustomImage.url"
        alt=""
        draggable="false"
      />
      <!-- fox -->
      <svg v-else-if="petId === 'fox'" viewBox="0 0 64 64" class="pet-svg" aria-hidden="true">
        <ellipse cx="32" cy="40" rx="18" ry="14" fill="#e07a3a" />
        <path d="M14 28 L22 12 L28 30 Z" fill="#c45d28" />
        <path d="M50 28 L42 12 L36 30 Z" fill="#c45d28" />
        <circle cx="32" cy="34" r="12" fill="#f0a06a" />
        <circle cx="27" cy="33" r="2.2" fill="#2a1a12" />
        <circle cx="37" cy="33" r="2.2" fill="#2a1a12" />
        <ellipse cx="32" cy="38" rx="3" ry="2" fill="#2a1a12" />
        <path d="M24 42 Q32 46 40 42" fill="none" stroke="#2a1a12" stroke-width="1.5" stroke-linecap="round" />
      </svg>
      <!-- owl -->
      <svg v-else-if="petId === 'owl'" viewBox="0 0 64 64" class="pet-svg" aria-hidden="true">
        <ellipse cx="32" cy="38" rx="16" ry="18" fill="#6b5b4a" />
        <circle cx="24" cy="30" r="9" fill="#f5e6c8" />
        <circle cx="40" cy="30" r="9" fill="#f5e6c8" />
        <circle cx="24" cy="30" r="4" fill="#2c241c" />
        <circle cx="40" cy="30" r="4" fill="#2c241c" />
        <circle cx="25" cy="29" r="1.2" fill="#fff" />
        <circle cx="41" cy="29" r="1.2" fill="#fff" />
        <path d="M32 34 L28 40 L36 40 Z" fill="#d97706" />
        <path d="M18 20 L24 26" stroke="#6b5b4a" stroke-width="3" stroke-linecap="round" />
        <path d="M46 20 L40 26" stroke="#6b5b4a" stroke-width="3" stroke-linecap="round" />
      </svg>
      <!-- bot -->
      <svg v-else-if="petId === 'bot'" viewBox="0 0 64 64" class="pet-svg" aria-hidden="true">
        <rect x="16" y="22" width="32" height="28" rx="8" fill="#4f6bff" />
        <rect x="20" y="28" width="24" height="12" rx="4" fill="#dbe4ff" />
        <circle cx="26" cy="34" r="2.5" fill="#1e293b" />
        <circle cx="38" cy="34" r="2.5" fill="#1e293b" />
        <rect x="26" y="44" width="12" height="3" rx="1.5" fill="#93a4ff" />
        <line x1="32" y1="14" x2="32" y2="22" stroke="#7c93ff" stroke-width="2" />
        <circle cx="32" cy="12" r="3" fill="#fbbf24" />
        <rect x="10" y="30" width="6" height="12" rx="3" fill="#7c93ff" />
        <rect x="48" y="30" width="6" height="12" rx="3" fill="#7c93ff" />
      </svg>
      <span v-else class="pet-custom-empty">?</span>
      <span class="pet-bounce" />
      <span v-if="petId === 'custom'" class="pet-status-dot" :class="`st-${taskStatus}`" />
    </div>

    <div
      v-show="showTip"
      :class="['pet-tip', { flip: tipPlace.flip, below: tipPlace.below }]"
      role="tooltip"
      :aria-label="t('desktopDecor.tip.title')"
    >
      <div class="pet-tip-head">
        <strong>{{ petTitle }}</strong>
      </div>
      <p class="pet-tip-lead">{{ t('desktopDecor.tip.lead') }}</p>
      <dl class="pet-tip-list">
        <div v-for="row in tipLines" :key="row.label" class="pet-tip-row">
          <dt>{{ row.label }}</dt>
          <dd :title="row.value">{{ row.value }}</dd>
        </div>
      </dl>
    </div>
  </div>
</template>

<style scoped>
.pet-root {
  position: fixed;
  z-index: 9000;
  width: 72px;
  height: 72px;
  pointer-events: none;
}
.pet {
  pointer-events: auto;
  width: 72px;
  height: 72px;
  border: 0;
  padding: 0;
  border-radius: 20px;
  background: color-mix(in srgb, var(--panel-bg) 78%, transparent);
  box-shadow:
    0 8px 24px rgba(15, 23, 42, 0.18),
    inset 0 0 0 1px color-mix(in srgb, var(--border-strong) 80%, transparent);
  cursor: grab;
  display: grid;
  place-items: center;
  position: relative;
  -webkit-app-region: no-drag;
  user-select: none;
  touch-action: none;
}
.pet.custom {
  padding: 4px;
}
.pet:hover,
.pet-root.tip .pet {
  transform: translateY(-1px);
}
.pet.dragging {
  cursor: grabbing;
  transform: scale(1.04);
}
.pet-dismiss {
  pointer-events: auto;
  position: absolute;
  top: -6px;
  right: -6px;
  z-index: 2;
  width: 20px;
  height: 20px;
  border: 0;
  border-radius: 999px;
  background: var(--panel-bg);
  color: var(--text-muted);
  box-shadow: 0 0 0 1px var(--border-strong);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: grid;
  place-items: center;
  opacity: 0;
  transition: opacity 0.12s ease;
}
.pet:hover .pet-dismiss,
.pet-root.tip .pet-dismiss {
  opacity: 1;
}
.pet-dismiss:hover {
  color: #fff;
  background: #e81123;
  box-shadow: none;
}
.pet-svg {
  width: 52px;
  height: 52px;
  display: block;
}
.pet-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 14px;
  pointer-events: none;
  display: block;
}
.pet-custom-empty {
  font-size: 22px;
  color: var(--text-muted);
}
.pet-status-dot {
  position: absolute;
  left: 6px;
  bottom: 6px;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  border: 2px solid var(--panel-bg);
  background: var(--text-muted);
}
.pet-status-dot.st-idle { background: #94a3b8; }
.pet-status-dot.st-busy { background: #3b82f6; }
.pet-status-dot.st-waiting { background: #f59e0b; }
.pet-status-dot.st-success { background: #22c55e; }
.pet-status-dot.st-error { background: #ef4444; }
.pet-bounce {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  animation: pet-idle 2.8s ease-in-out infinite;
}
.pet.dragging .pet-bounce,
.pet.custom .pet-bounce {
  animation: none;
}
@keyframes pet-idle {
  0%,
  100% {
    box-shadow: inset 0 0 0 0 transparent;
  }
  50% {
    box-shadow: inset 0 -6px 12px color-mix(in srgb, var(--primary) 12%, transparent);
  }
}
.pet-tip {
  pointer-events: auto;
  position: absolute;
  left: 80px;
  bottom: 0;
  width: min(260px, calc(100vw - 100px));
  max-height: min(320px, calc(100vh - 24px));
  overflow: auto;
  padding: 10px 12px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--panel-bg) 94%, transparent);
  border: var(--border-width) solid var(--border-strong);
  box-shadow: var(--dropdown-shadow);
  color: var(--text);
  backdrop-filter: blur(10px);
}
.pet-tip.flip {
  left: auto;
  right: 80px;
}
.pet-tip.below {
  bottom: auto;
  top: 0;
}
.pet-tip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.pet-tip-head strong {
  color: var(--text-h);
  font-size: 13px;
}
.pet-tip-lead {
  margin: 0 0 8px;
  font-size: 11px;
  color: var(--text-muted);
}
.pet-tip-list {
  margin: 0;
  display: grid;
  gap: 6px;
}
.pet-tip-row {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 8px;
  font-size: 12px;
}
.pet-tip-row dt {
  color: var(--text-muted);
}
.pet-tip-row dd {
  margin: 0;
  color: var(--text-h);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
