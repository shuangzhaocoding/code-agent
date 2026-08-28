<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import { isInterestingPort, usePortsWatch, type PortItem } from '@/composables/usePortsWatch'

type PortNotice = PortItem & { id: string; compact: boolean; secondsLeft: number }

const AUTO_CLOSE_SEC = 10
const COMPACT_DELAY_MS = 700

const { t } = useI18n()
const { ports, markPortHighlighted } = usePortsWatch()
const notices = ref<PortNotice[]>([])
const known = ref<Set<number> | null>(null)
let seq = 0

const countdownTimers = new Map<string, ReturnType<typeof setInterval>>()
const compactTimers = new Map<string, ReturnType<typeof setTimeout>>()

const origin = computed(() => (typeof location !== 'undefined' ? location.origin : ''))

function setNotice(id: string, patch: Partial<PortNotice>) {
  notices.value = notices.value.map((n) => (n.id === id ? { ...n, ...patch } : n))
}

function clearNoticeTimers(id: string) {
  const countdown = countdownTimers.get(id)
  if (countdown) {
    clearInterval(countdown)
    countdownTimers.delete(id)
  }
  const compact = compactTimers.get(id)
  if (compact) {
    clearTimeout(compact)
    compactTimers.delete(id)
  }
}

function dismiss(id: string) {
  clearNoticeTimers(id)
  notices.value = notices.value.filter((n) => n.id !== id)
}

function pushNotice(item: PortItem) {
  markPortHighlighted(item.port)
  const id = `${item.port}-${++seq}`
  const notice: PortNotice = {
    ...item,
    id,
    compact: false,
    secondsLeft: AUTO_CLOSE_SEC,
  }
  notices.value = [...notices.value.filter((n) => n.port !== item.port), notice].slice(-4)

  compactTimers.set(
    id,
    setTimeout(() => {
      compactTimers.delete(id)
      if (notices.value.some((n) => n.id === id)) setNotice(id, { compact: true })
    }, COMPACT_DELAY_MS),
  )

  countdownTimers.set(
    id,
    setInterval(() => {
      const current = notices.value.find((n) => n.id === id)
      if (!current) {
        clearNoticeTimers(id)
        return
      }
      const next = current.secondsLeft - 1
      if (next <= 0) {
        dismiss(id)
        return
      }
      setNotice(id, { secondsLeft: next })
    }, 1000),
  )
}

function openPreview(item: PortNotice) {
  window.open(item.preview_path || `/api/preview/${item.port}/`, '_blank', 'noopener,noreferrer')
  dismiss(item.id)
}

async function copyAddress(item: PortNotice) {
  const preview = `${origin.value}${item.preview_path}`
  try {
    await navigator.clipboard.writeText(preview)
  } catch {
    try {
      await navigator.clipboard.writeText(item.url)
    } catch {
      /* ignore */
    }
  }
}

watch(
  ports,
  (list) => {
    const interesting = list.filter(isInterestingPort)
    const next = new Set(interesting.map((p) => p.port))
    if (known.value === null) {
      known.value = next
      return
    }
    for (const item of interesting) {
      if (!known.value.has(item.port)) pushNotice(item)
    }
    known.value = next
  },
  { deep: true },
)

onBeforeUnmount(() => {
  for (const id of [...countdownTimers.keys()]) clearNoticeTimers(id)
  for (const id of [...compactTimers.keys()]) clearNoticeTimers(id)
})
</script>

<template>
  <Teleport to="body">
    <div class="port-notify-stack" aria-live="polite">
      <TransitionGroup name="port-toast">
        <article v-for="item in notices" :key="item.id" class="port-toast" :class="{ compact: item.compact }">
          <header>
            <AppIcon name="ports" :size="item.compact ? 14 : 16" />
            <div class="titles">
              <strong>{{ t('ports.found', { port: item.port }) }}</strong>
              <span>{{ item.process || 'unknown' }} · {{ item.address }}</span>
            </div>
            <span class="countdown" :title="t('ports.autoClose', { n: item.secondsLeft })">
              {{ t('ports.autoCloseShort', { n: item.secondsLeft }) }}
            </span>
            <button type="button" class="icon" :title="t('common.close')" @click="dismiss(item.id)">×</button>
          </header>
          <div v-if="!item.compact" class="urls">
            <div class="row">
              <span class="label">{{ t('ports.open') }}</span>
              <code :title="`${origin}${item.preview_path}`">{{ origin }}{{ item.preview_path }}</code>
            </div>
            <div class="row">
              <span class="label">{{ t('ports.local') }}</span>
              <code :title="item.url">{{ item.url }}</code>
            </div>
          </div>
          <footer>
            <button v-if="!item.compact" type="button" class="btn btn-ghost" @click="copyAddress(item)">
              {{ t('ports.copyAddr') }}
            </button>
            <button type="button" class="btn btn-primary" @click="openPreview(item)">{{ t('ports.open') }}</button>
          </footer>
        </article>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.port-notify-stack {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 140;
  display: flex;
  flex-direction: column-reverse;
  gap: 10px;
  width: min(380px, calc(100vw - 24px));
  pointer-events: none;
}
.port-toast {
  pointer-events: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: var(--shadow-md);
  padding: 12px 14px;
  color: var(--text);
  transition: padding 0.22s ease, max-height 0.22s ease;
  overflow: hidden;
}
.port-toast.compact {
  padding: 8px 10px;
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  box-shadow: 0 6px 20px color-mix(in srgb, var(--primary) 18%, transparent);
}
header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.titles {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.titles strong {
  font-size: 13.5px;
  color: var(--text-h);
}
.port-toast.compact .titles strong {
  font-size: 12.5px;
}
.titles span {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.port-toast.compact .titles span {
  font-size: 11px;
}
.countdown {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  font-family: var(--mono);
  color: var(--primary);
  background: var(--primary-soft);
  border-radius: 999px;
  padding: 2px 8px;
  line-height: 1.4;
  align-self: center;
}
.icon {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
  flex-shrink: 0;
}
.urls {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.row {
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 8px;
  align-items: center;
}
.label {
  font-size: 11px;
  color: var(--text-secondary);
}
code {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--text-h);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
}
footer {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.port-toast.compact footer {
  margin-top: 8px;
}
.port-toast.compact .btn {
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
}
.port-toast-enter-active,
.port-toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.port-toast-enter-from,
.port-toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
