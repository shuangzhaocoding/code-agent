<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { usePortsWatch, type PortItem } from '@/composables/usePortsWatch'

type PortNotice = PortItem & { id: string }

const SYSTEM_PORTS = new Set([22, 25, 53, 111, 123, 135, 139, 445, 631, 5353])

const { ports } = usePortsWatch()
const notices = ref<PortNotice[]>([])
const known = ref<Set<number> | null>(null)
let seq = 0

const origin = computed(() => (typeof location !== 'undefined' ? location.origin : ''))

function isInteresting(item: PortItem): boolean {
  if (item.self) return false
  if (SYSTEM_PORTS.has(item.port)) return false
  return true
}

function pushNotice(item: PortItem) {
  const id = `${item.port}-${++seq}`
  notices.value = [...notices.value.filter((n) => n.port !== item.port), { ...item, id }].slice(-4)
}

function dismiss(id: string) {
  notices.value = notices.value.filter((n) => n.id !== id)
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
    const interesting = list.filter(isInteresting)
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
</script>

<template>
  <Teleport to="body">
    <div class="port-notify-stack" aria-live="polite">
      <TransitionGroup name="port-toast">
        <article v-for="item in notices" :key="item.id" class="port-toast">
          <header>
            <AppIcon name="ports" :size="16" />
            <div class="titles">
              <strong>发现新端口 {{ item.port }}</strong>
              <span>{{ item.process || 'unknown' }} · {{ item.address }}</span>
            </div>
            <button type="button" class="icon" title="关闭" @click="dismiss(item.id)">×</button>
          </header>
          <div class="urls">
            <div class="row">
              <span class="label">打开</span>
              <code :title="`${origin}${item.preview_path}`">{{ origin }}{{ item.preview_path }}</code>
            </div>
            <div class="row">
              <span class="label">本机</span>
              <code :title="item.url">{{ item.url }}</code>
            </div>
          </div>
          <footer>
            <button type="button" class="btn" @click="copyAddress(item)">复制地址</button>
            <button type="button" class="btn primary" @click="openPreview(item)">打开</button>
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
.titles span {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.icon {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
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
.btn {
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-h);
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  font-size: 12.5px;
  cursor: pointer;
}
.btn.primary {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
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
