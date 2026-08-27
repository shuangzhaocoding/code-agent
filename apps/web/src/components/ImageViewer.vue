<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'

export type ImageViewerItem = {
  src: string
  alt?: string
  title?: string
}

const props = withDefaults(
  defineProps<{
    src?: string
    alt?: string
    title?: string
    items?: ImageViewerItem[]
    index?: number
    /** Modal mode: controlled by v-model:open */
    open?: boolean
    /** Inline mode inside a panel (no teleport overlay) */
    embedded?: boolean
  }>(),
  {
    src: '',
    alt: '',
    title: '',
    items: () => [],
    index: 0,
    open: false,
    embedded: false,
  },
)

const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:index': [value: number]
  close: []
}>()

const { t } = useI18n()

const viewportRef = ref<HTMLElement | null>(null)
const imageRef = ref<HTMLImageElement | null>(null)
const scale = ref(1)
const tx = ref(0)
const ty = ref(0)
const dragging = ref(false)

const MIN_SCALE = 0.05
const MAX_SCALE = 12

let dragStart: { x: number; y: number; tx: number; ty: number } | null = null

const zoomLabel = computed(() => `${Math.round(scale.value * 100)}%`)

const galleryItems = computed(() => {
  if (props.items.length) return props.items.filter((item) => item.src)
  if (props.src) return [{ src: props.src, alt: props.alt, title: props.title }]
  return []
})

const hasGallery = computed(() => galleryItems.value.length > 1)

const currentIndex = computed({
  get: () => {
    const max = galleryItems.value.length - 1
    if (max < 0) return 0
    return Math.min(Math.max(0, props.index), max)
  },
  set: (value: number) => emit('update:index', value),
})

const currentItem = computed(() => galleryItems.value[currentIndex.value] ?? galleryItems.value[0])

const currentSrc = computed(() => currentItem.value?.src ?? '')
const currentAlt = computed(() => currentItem.value?.alt ?? props.alt ?? '')
const currentTitle = computed(() => currentItem.value?.title ?? currentItem.value?.alt ?? props.title ?? '')

const counterLabel = computed(() => {
  if (!hasGallery.value) return ''
  return `${currentIndex.value + 1} / ${galleryItems.value.length}`
})

const imageStyle = computed(() => ({
  transform: `translate(${tx.value}px, ${ty.value}px) scale(${scale.value})`,
  transformOrigin: '0 0',
}))

function clampScale(value: number) {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))
}

function fitImage() {
  const viewport = viewportRef.value
  const image = imageRef.value
  if (!viewport || !image || !image.naturalWidth || !image.naturalHeight) return
  const vw = viewport.clientWidth
  const vh = viewport.clientHeight
  const iw = image.naturalWidth
  const ih = image.naturalHeight
  const next = Math.min(vw / iw, vh / ih, 1)
  scale.value = next
  tx.value = (vw - iw * next) / 2
  ty.value = (vh - ih * next) / 2
}

function resetActualSize() {
  const viewport = viewportRef.value
  const image = imageRef.value
  if (!viewport || !image || !image.naturalWidth || !image.naturalHeight) return
  scale.value = 1
  tx.value = (viewport.clientWidth - image.naturalWidth) / 2
  ty.value = (viewport.clientHeight - image.naturalHeight) / 2
}

function zoomAt(factor: number, clientX?: number, clientY?: number) {
  const viewport = viewportRef.value
  if (!viewport) return
  const rect = viewport.getBoundingClientRect()
  const px = clientX != null ? clientX - rect.left : rect.width / 2
  const py = clientY != null ? clientY - rect.top : rect.height / 2
  const next = clampScale(scale.value * factor)
  const ratio = next / scale.value
  tx.value = px - ratio * (px - tx.value)
  ty.value = py - ratio * (py - ty.value)
  scale.value = next
}

function zoomIn() {
  zoomAt(1.2)
}

function zoomOut() {
  zoomAt(1 / 1.2)
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
  zoomAt(factor, e.clientX, e.clientY)
}

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  dragging.value = true
  dragStart = { x: e.clientX, y: e.clientY, tx: tx.value, ty: ty.value }
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  if (!dragStart) return
  tx.value = dragStart.tx + (e.clientX - dragStart.x)
  ty.value = dragStart.ty + (e.clientY - dragStart.y)
}

function onPointerUp(e: PointerEvent) {
  dragging.value = false
  dragStart = null
  ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
}

function onDoubleClick(e: MouseEvent) {
  if (scale.value > 1.05) fitImage()
  else zoomAt(2, e.clientX, e.clientY)
}

function onImageLoad() {
  fitImage()
}

function resetView() {
  scale.value = 1
  tx.value = 0
  ty.value = 0
}

function showIndex(next: number) {
  const max = galleryItems.value.length - 1
  if (max < 0) return
  const clamped = Math.min(Math.max(0, next), max)
  if (clamped === currentIndex.value) return
  resetView()
  currentIndex.value = clamped
}

function showPrev() {
  showIndex(currentIndex.value - 1)
}

function showNext() {
  showIndex(currentIndex.value + 1)
}

function close() {
  emit('update:open', false)
  emit('close')
}

function onKeydown(e: KeyboardEvent) {
  if (props.embedded || !props.open) return
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
  } else if (e.key === 'ArrowLeft' && hasGallery.value) {
    e.preventDefault()
    showPrev()
  } else if (e.key === 'ArrowRight' && hasGallery.value) {
    e.preventDefault()
    showNext()
  } else if (e.key === '+' || e.key === '=') {
    e.preventDefault()
    zoomIn()
  } else if (e.key === '-') {
    e.preventDefault()
    zoomOut()
  } else if (e.key === '0') {
    e.preventDefault()
    fitImage()
  }
}

watch(
  () => props.open,
  (open, _, onCleanup) => {
    if (props.embedded) return
    if (!open) return
    window.addEventListener('keydown', onKeydown)
    nextTick(() => fitImage())
    onCleanup(() => window.removeEventListener('keydown', onKeydown))
  },
)

watch(
  () => currentSrc.value,
  () => nextTick(() => fitImage()),
)

defineExpose({ fitImage, resetActualSize, zoomIn, zoomOut })
</script>

<template>
  <Teleport v-if="!embedded" to="body">
    <Transition name="viewer-fade">
      <div v-if="open" class="image-viewer-overlay" @click.self="close">
        <div class="image-viewer-shell" role="dialog" aria-modal="true" :aria-label="currentTitle || currentAlt || t('preview.imageViewer')">
          <button
            v-if="hasGallery && currentIndex > 0"
            type="button"
            class="viewer-nav viewer-nav-prev"
            :title="t('preview.prevImage')"
            @click="showPrev"
          >
            <AppIcon name="arrow-left" :size="20" />
          </button>
          <button
            v-if="hasGallery && currentIndex < galleryItems.length - 1"
            type="button"
            class="viewer-nav viewer-nav-next"
            :title="t('preview.nextImage')"
            @click="showNext"
          >
            <AppIcon name="chevron-right" :size="20" />
          </button>
          <div
            ref="viewportRef"
            class="image-viewer-viewport"
            :class="{ dragging }"
            @wheel="onWheel"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointercancel="onPointerUp"
            @dblclick="onDoubleClick"
          >
            <img
              ref="imageRef"
              :key="currentSrc"
              :src="currentSrc"
              :alt="currentAlt"
              draggable="false"
              :style="imageStyle"
              @load="onImageLoad"
            />
          </div>
          <footer class="image-viewer-toolbar" @click.stop>
            <span v-if="counterLabel" class="viewer-counter">{{ counterLabel }}</span>
            <span class="image-viewer-title" :title="currentTitle || currentAlt">{{ currentTitle || currentAlt || t('preview.imageViewer') }}</span>
            <div class="image-viewer-actions">
              <template v-if="hasGallery">
                <button
                  type="button"
                  class="viewer-btn"
                  :title="t('preview.prevImage')"
                  :disabled="currentIndex <= 0"
                  @click="showPrev"
                >
                  <AppIcon name="arrow-left" :size="16" />
                </button>
                <button
                  type="button"
                  class="viewer-btn"
                  :title="t('preview.nextImage')"
                  :disabled="currentIndex >= galleryItems.length - 1"
                  @click="showNext"
                >
                  <AppIcon name="chevron-right" :size="16" />
                </button>
                <span class="viewer-actions-sep" aria-hidden="true" />
              </template>
              <button type="button" class="viewer-btn" :title="t('preview.zoomOut')" @click="zoomOut">
                <AppIcon name="minus" :size="16" />
              </button>
              <span class="viewer-zoom">{{ zoomLabel }}</span>
              <button type="button" class="viewer-btn" :title="t('preview.zoomIn')" @click="zoomIn">
                <AppIcon name="plus" :size="16" />
              </button>
              <button type="button" class="viewer-btn" :title="t('preview.fitWindow')" @click="fitImage">
                <AppIcon name="expand-all" :size="16" />
              </button>
              <button type="button" class="viewer-btn" :title="t('preview.actualSize')" @click="resetActualSize">1:1</button>
              <a
                v-if="currentSrc"
                class="viewer-btn viewer-link"
                :href="currentSrc"
                target="_blank"
                rel="noopener noreferrer"
                :title="t('common.open')"
              >
                <AppIcon name="globe" :size="16" />
              </a>
              <button type="button" class="viewer-btn" :title="t('common.close')" @click="close">
                <AppIcon name="close" :size="16" />
              </button>
            </div>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>

  <div v-else class="image-viewer-embedded">
    <div
      ref="viewportRef"
      class="image-viewer-viewport embedded"
      :class="{ dragging }"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @dblclick="onDoubleClick"
    >
      <img
        ref="imageRef"
        :key="currentSrc"
        :src="currentSrc"
        :alt="currentAlt"
        draggable="false"
        :style="imageStyle"
        @load="onImageLoad"
      />
    </div>
    <footer class="image-viewer-toolbar embedded" @click.stop>
      <span class="image-viewer-title" :title="currentTitle || currentAlt">{{ currentTitle || currentAlt }}</span>
      <div class="image-viewer-actions">
        <template v-if="hasGallery">
          <button
            type="button"
            class="viewer-btn"
            :title="t('preview.prevImage')"
            :disabled="currentIndex <= 0"
            @click="showPrev"
          >
            <AppIcon name="arrow-left" :size="16" />
          </button>
          <button
            type="button"
            class="viewer-btn"
            :title="t('preview.nextImage')"
            :disabled="currentIndex >= galleryItems.length - 1"
            @click="showNext"
          >
            <AppIcon name="chevron-right" :size="16" />
          </button>
          <span class="viewer-actions-sep" aria-hidden="true" />
        </template>
        <button type="button" class="viewer-btn" :title="t('preview.zoomOut')" @click="zoomOut">
          <AppIcon name="minus" :size="16" />
        </button>
        <span class="viewer-zoom">{{ zoomLabel }}</span>
        <button type="button" class="viewer-btn" :title="t('preview.zoomIn')" @click="zoomIn">
          <AppIcon name="plus" :size="16" />
        </button>
        <button type="button" class="viewer-btn" :title="t('preview.fitWindow')" @click="fitImage">
          <AppIcon name="expand-all" :size="16" />
        </button>
        <button type="button" class="viewer-btn" :title="t('preview.actualSize')" @click="resetActualSize">1:1</button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.image-viewer-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: rgba(8, 10, 16, 0.88);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: stretch;
  justify-content: center;
  padding: 0;
  box-sizing: border-box;
}

.image-viewer-shell {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: transparent;
}

.image-viewer-embedded {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  background: var(--editor-bg);
}

.image-viewer-toolbar {
  position: absolute;
  left: 50%;
  bottom: 24px;
  z-index: 2;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: calc(100% - 32px);
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(12, 14, 20, 0.62);
  backdrop-filter: blur(10px);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.35);
  flex-shrink: 0;
}

.image-viewer-toolbar.embedded {
  bottom: 14px;
  padding: 6px 12px;
  background: rgba(12, 14, 20, 0.72);
}

.viewer-counter {
  flex-shrink: 0;
  font-size: 12px;
  font-family: var(--mono);
  color: rgba(255, 255, 255, 0.72);
}

.viewer-nav {
  position: absolute;
  top: 50%;
  z-index: 3;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: rgba(12, 14, 20, 0.55);
  backdrop-filter: blur(8px);
  color: rgba(255, 255, 255, 0.88);
  cursor: pointer;
}

.viewer-nav:hover {
  background: rgba(12, 14, 20, 0.78);
  color: #fff;
}

.viewer-nav-prev {
  left: 20px;
}

.viewer-nav-next {
  right: 20px;
}

.image-viewer-title {
  flex: 1;
  min-width: 0;
  max-width: 240px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.88);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-viewer-toolbar.embedded .image-viewer-title {
  max-width: 180px;
}

.image-viewer-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.viewer-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 30px;
  height: 30px;
  padding: 0 8px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
  cursor: pointer;
  font-size: 12px;
  text-decoration: none;
}

.viewer-btn:hover {
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
}

.viewer-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.viewer-btn:disabled:hover {
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
}

.viewer-actions-sep {
  width: 1px;
  height: 18px;
  margin: 0 2px;
  background: rgba(255, 255, 255, 0.18);
  flex-shrink: 0;
}

.viewer-link:hover {
  color: #fff;
}

.viewer-zoom {
  min-width: 44px;
  text-align: center;
  font-size: 12px;
  font-family: var(--mono);
  color: rgba(255, 255, 255, 0.72);
}

.image-viewer-viewport {
  position: relative;
  flex: 1;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  cursor: grab;
  touch-action: none;
  background: transparent;
}

.image-viewer-viewport.embedded {
  min-height: 240px;
  background:
    linear-gradient(45deg, var(--bg-muted) 25%, transparent 25%),
    linear-gradient(-45deg, var(--bg-muted) 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, var(--bg-muted) 75%),
    linear-gradient(-45deg, transparent 75%, var(--bg-muted) 75%);
  background-size: 16px 16px;
  background-position: 0 0, 0 8px, 8px -8px, -8px 0;
  background-color: var(--editor-bg);
}

.image-viewer-viewport.dragging {
  cursor: grabbing;
}

.image-viewer-viewport img {
  position: absolute;
  top: 0;
  left: 0;
  max-width: none;
  max-height: none;
  user-select: none;
  pointer-events: none;
  box-shadow: var(--shadow-md);
}

.viewer-fade-enter-active,
.viewer-fade-leave-active {
  transition: opacity 0.16s ease;
}

.viewer-fade-enter-from,
.viewer-fade-leave-to {
  opacity: 0;
}
</style>
