<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'

export type CropKind = 'wallpaper' | 'pet'

const props = defineProps<{
  open: boolean
  file: File | null
  /** Existing image URL for re-crop after upload */
  srcUrl?: string | null
  kind: CropKind
  /** upload = first-time; edit = re-crop saved image */
  mode?: 'upload' | 'edit'
}>()

const emit = defineEmits<{
  close: []
  confirm: [file: File]
}>()

const { t } = useI18n()

const PRESETS = {
  wallpaper: { aspect: 16 / 9, outW: 1920, outH: 1080, labelKey: 'desktopDecor.crop.wallpaperSize' },
  pet: { aspect: 1, outW: 384, outH: 384, labelKey: 'desktopDecor.crop.petSize' },
} as const

const stageRef = ref<HTMLDivElement | null>(null)
const imgNatural = ref({ w: 0, h: 0 })
const objectUrl = ref('')
const ownsObjectUrl = ref(false)
const scale = ref(1)
const minScale = ref(1)
const offset = ref({ x: 0, y: 0 })
const dragging = ref(false)
const busy = ref(false)
let dragStart = { x: 0, y: 0 }
let offsetStart = { x: 0, y: 0 }

const hasSource = computed(() => Boolean(props.file || props.srcUrl))
const applyLabel = computed(() =>
  busy.value
    ? t('desktopDecor.crop.working')
    : props.mode === 'edit'
      ? t('desktopDecor.crop.save')
      : t('desktopDecor.crop.apply'),
)

const preset = computed(() => PRESETS[props.kind])
const sizeHint = computed(() =>
  t(preset.value.labelKey, { w: preset.value.outW, h: preset.value.outH }),
)

const frameStyle = computed(() => {
  const aspect = preset.value.aspect
  // Fit frame inside dialog stage area (~520×320)
  const maxW = 520
  const maxH = 320
  let w = maxW
  let h = w / aspect
  if (h > maxH) {
    h = maxH
    w = h * aspect
  }
  return { width: `${Math.round(w)}px`, height: `${Math.round(h)}px` }
})

const frameSize = computed(() => {
  const aspect = preset.value.aspect
  const maxW = 520
  const maxH = 320
  let w = maxW
  let h = w / aspect
  if (h > maxH) {
    h = maxH
    w = h * aspect
  }
  return { w: Math.round(w), h: Math.round(h) }
})

const imgStyle = computed(() => {
  const { w, h } = imgNatural.value
  if (!w || !h) return {}
  const dispW = w * scale.value
  const dispH = h * scale.value
  return {
    width: `${dispW}px`,
    height: `${dispH}px`,
    transform: `translate(${offset.value.x}px, ${offset.value.y}px)`,
  }
})

function revoke() {
  if (ownsObjectUrl.value && objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value)
  }
  objectUrl.value = ''
  ownsObjectUrl.value = false
}

function clampOffset() {
  const { w, h } = imgNatural.value
  const fw = frameSize.value.w
  const fh = frameSize.value.h
  const dw = w * scale.value
  const dh = h * scale.value
  const minX = Math.min(0, fw - dw)
  const minY = Math.min(0, fh - dh)
  offset.value = {
    x: Math.min(0, Math.max(minX, offset.value.x)),
    y: Math.min(0, Math.max(minY, offset.value.y)),
  }
}

function fitImage() {
  const { w, h } = imgNatural.value
  const fw = frameSize.value.w
  const fh = frameSize.value.h
  if (!w || !h || !fw || !fh) return
  const cover = Math.max(fw / w, fh / h)
  minScale.value = cover
  scale.value = cover
  offset.value = {
    x: (fw - w * cover) / 2,
    y: (fh - h * cover) / 2,
  }
  clampOffset()
}

async function decodeFromUrl(url: string) {
  await new Promise<void>((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      imgNatural.value = { w: img.naturalWidth, h: img.naturalHeight }
      fitImage()
      resolve()
    }
    img.onerror = () => reject(new Error('load'))
    img.src = url
  })
}

async function loadFile(file: File) {
  revoke()
  objectUrl.value = URL.createObjectURL(file)
  ownsObjectUrl.value = true
  await decodeFromUrl(objectUrl.value)
}

async function loadSrcUrl(url: string) {
  revoke()
  const res = await fetch(url)
  if (!res.ok) throw new Error('load')
  const blob = await res.blob()
  objectUrl.value = URL.createObjectURL(blob)
  ownsObjectUrl.value = true
  await decodeFromUrl(objectUrl.value)
}

watch(
  () => [props.open, props.file, props.srcUrl] as const,
  async ([open, file, srcUrl]) => {
    if (!open || (!file && !srcUrl)) {
      revoke()
      return
    }
    try {
      if (file) await loadFile(file)
      else if (srcUrl) await loadSrcUrl(srcUrl)
    } catch {
      emit('close')
    }
  },
)

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const next = Math.min(8, Math.max(minScale.value, scale.value * (e.deltaY > 0 ? 0.92 : 1.08)))
  const fw = frameSize.value.w
  const fh = frameSize.value.h
  const cx = fw / 2
  const cy = fh / 2
  const ratio = next / scale.value
  offset.value = {
    x: cx - (cx - offset.value.x) * ratio,
    y: cy - (cy - offset.value.y) * ratio,
  }
  scale.value = next
  clampOffset()
}

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  dragging.value = true
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  dragStart = { x: e.clientX, y: e.clientY }
  offsetStart = { ...offset.value }
}

function onPointerMove(e: PointerEvent) {
  if (!dragging.value) return
  offset.value = {
    x: offsetStart.x + (e.clientX - dragStart.x),
    y: offsetStart.y + (e.clientY - dragStart.y),
  }
  clampOffset()
}

function onPointerUp(e: PointerEvent) {
  if (!dragging.value) return
  dragging.value = false
  try {
    ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
  } catch {
    /* ignore */
  }
}

function onScaleInput(e: Event) {
  const next = Number((e.target as HTMLInputElement).value)
  const fw = frameSize.value.w
  const fh = frameSize.value.h
  const cx = fw / 2
  const cy = fh / 2
  const ratio = next / scale.value
  offset.value = {
    x: cx - (cx - offset.value.x) * ratio,
    y: cy - (cy - offset.value.y) * ratio,
  }
  scale.value = next
  clampOffset()
}

async function confirmCrop() {
  if ((!props.file && !props.srcUrl) || busy.value) return
  const { w, h } = imgNatural.value
  const fw = frameSize.value.w
  const fh = frameSize.value.h
  if (!w || !h) return
  busy.value = true
  try {
    const sx = Math.max(0, -offset.value.x / scale.value)
    const sy = Math.max(0, -offset.value.y / scale.value)
    const sw = Math.min(w - sx, fw / scale.value)
    const sh = Math.min(h - sy, fh / scale.value)
    const outW = preset.value.outW
    const outH = preset.value.outH
    const canvas = document.createElement('canvas')
    canvas.width = outW
    canvas.height = outH
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('canvas')
    const img = new Image()
    img.src = objectUrl.value
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('load'))
      if (img.complete) resolve()
    })
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, outW, outH)
    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error('blob'))),
        'image/jpeg',
        0.9,
      )
    })
    const base =
      (props.file?.name || props.kind).replace(/\.[^.]+$/, '') || props.kind
    const out = new File([blob], `${base}-crop.jpg`, { type: 'image/jpeg' })
    emit('confirm', out)
  } catch {
    /* parent will toast if needed */
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  if (props.open && props.file) void loadFile(props.file)
  else if (props.open && props.srcUrl) void loadSrcUrl(props.srcUrl)
})
onBeforeUnmount(revoke)
</script>

<template>
  <Teleport to="body">
    <div v-if="open && hasSource" class="crop-mask" @click.self="emit('close')">
      <div class="crop-sheet" role="dialog" aria-modal="true" :aria-label="t('desktopDecor.crop.title')">
        <header class="crop-head">
          <div>
            <h2>{{ t('desktopDecor.crop.title') }}</h2>
            <p class="crop-hint">{{ sizeHint }}</p>
          </div>
          <button type="button" class="crop-x" :aria-label="t('common.close')" @click="emit('close')">
            <AppIcon name="close" :size="16" />
          </button>
        </header>

        <div class="crop-body">
          <div
            ref="stageRef"
            class="crop-frame"
            :style="frameStyle"
            @wheel.prevent="onWheel"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointercancel="onPointerUp"
          >
            <img v-if="objectUrl" class="crop-img" :src="objectUrl" alt="" draggable="false" :style="imgStyle" />
            <div class="crop-overlay" aria-hidden="true" />
          </div>
          <label class="crop-zoom">
            <span>{{ t('desktopDecor.crop.zoom') }}</span>
            <input
              type="range"
              :min="minScale"
              :max="Math.max(minScale * 4, minScale + 0.01)"
              :step="0.01"
              :value="scale"
              @input="onScaleInput"
            />
          </label>
          <p class="crop-tip">{{ t('desktopDecor.crop.tip') }}</p>
        </div>

        <footer class="crop-foot">
          <button type="button" class="btn-ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
          <button type="button" class="btn-primary" :disabled="busy" @click="confirmCrop">
            {{ applyLabel }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.crop-mask {
  position: fixed;
  inset: 0;
  z-index: 11000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(4px);
}
.crop-sheet {
  width: min(640px, 100%);
  border-radius: 14px;
  border: var(--border-width) solid var(--border-strong);
  background: var(--panel-bg);
  box-shadow: var(--dropdown-shadow);
  overflow: hidden;
}
.crop-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: var(--border-width) solid var(--border);
}
.crop-head h2 {
  margin: 0;
  font-size: 15px;
  color: var(--text-h);
}
.crop-hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
.crop-x {
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
}
.crop-x:hover {
  color: var(--text-h);
  background: var(--code-bg);
}
.crop-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px;
}
.crop-frame {
  position: relative;
  overflow: hidden;
  border-radius: 10px;
  border: 1px solid var(--border-strong);
  background: #0b0d12;
  cursor: grab;
  touch-action: none;
  user-select: none;
}
.crop-frame:active {
  cursor: grabbing;
}
.crop-img {
  position: absolute;
  left: 0;
  top: 0;
  max-width: none;
  pointer-events: none;
}
.crop-overlay {
  position: absolute;
  inset: 0;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.35);
  pointer-events: none;
}
.crop-zoom {
  display: flex;
  align-items: center;
  gap: 10px;
  width: min(520px, 100%);
  font-size: 12px;
  color: var(--text-muted);
}
.crop-zoom input {
  flex: 1;
}
.crop-tip {
  margin: 0;
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
}
.crop-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: var(--border-width) solid var(--border);
}
.btn-ghost,
.btn-primary {
  height: 32px;
  padding: 0 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
}
.btn-ghost {
  border: var(--border-width) solid var(--border);
  background: transparent;
  color: var(--text-h);
}
.btn-primary {
  border: 0;
  background: var(--primary);
  color: #fff;
  font-weight: 600;
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>
