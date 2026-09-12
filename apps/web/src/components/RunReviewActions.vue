<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore, type FileReview } from '@/stores/app'
import type { ChatMessage } from '@/protocol/applyEvent'
import AppIcon from '@/components/AppIcon.vue'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  message: ChatMessage
}>()

const { t } = useI18n()
const store = useAppStore()
const toast = useToast()

const pending = computed(() => store.pendingReviewsForMessage(props.message))
const count = computed(() => files.value.length)
const busy = ref(false)
const busyPath = ref('')
const open = ref(false)

const files = computed(() => {
  const map = new Map<string, FileReview[]>()
  for (const item of pending.value) {
    const list = map.get(item.path) || []
    list.push(item)
    map.set(item.path, list)
  }
  return [...map.entries()].map(([path, reviews]) => ({
    path,
    reviews,
    action: reviews[reviews.length - 1]?.action || 'edit',
  }))
})

function fileName(path: string) {
  const parts = path.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || path
}

function actionLabel(action: string) {
  if (action === 'delete') return t('chat.runActionDelete')
  if (action === 'create' || action === 'overwrite') return t('chat.runActionCreate')
  return t('chat.runActionEdit')
}

function actionIcon(action: string) {
  if (action === 'delete') return 'trash'
  if (action === 'create' || action === 'overwrite') return 'file-plus'
  return 'file-edit'
}

function toggle() {
  open.value = !open.value
}

async function withBusy(path: string | null, fn: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  busyPath.value = path || ''
  try {
    await fn()
  } finally {
    busy.value = false
    busyPath.value = ''
  }
}

async function rejectRun() {
  await withBusy(null, () => store.rejectReviewsForMessage(props.message))
}

async function acceptRun() {
  await withBusy(null, () => store.acceptReviewsForMessage(props.message))
}

async function acceptFile(item: { path: string; reviews: FileReview[] }) {
  await withBusy(item.path, async () => {
    for (const review of item.reviews) await store.acceptReview(review.path, review.blockId)
  })
}

async function rejectFile(item: { path: string; reviews: FileReview[] }) {
  await withBusy(item.path, async () => {
    for (const review of item.reviews) await store.rejectReview(review.path, review.blockId, { silent: true })
    toast.info(t('editor.reviewRejected', { path: item.path }))
  })
}

function openFile(path: string) {
  void store.openAgentFile(path)
}
</script>

<template>
  <div v-if="count" class="run-review" :class="{ open }" role="group" :aria-label="t('chat.rejectThisRun')">
    <div class="head">
      <button type="button" class="copy" :aria-expanded="open" @click="toggle">
        <AppIcon class="chevron" :name="open ? 'chevron-down' : 'chevron-right'" :size="14" />
        <AppIcon name="file-edit" :size="14" />
        <span>{{ t('chat.runChanges', { n: count }) }}</span>
        <em>{{ open ? t('chat.collapseRunChanges') : t('chat.expandRunChanges') }}</em>
      </button>
      <div class="actions">
        <button type="button" class="run-btn accept" :disabled="busy" @click.stop="acceptRun">
          {{ t('chat.acceptThisRun') }}
        </button>
        <button type="button" class="run-btn reject" :disabled="busy" @click.stop="rejectRun">
          {{ t('chat.rejectThisRun') }}
        </button>
      </div>
    </div>

    <ul v-if="open" class="file-list">
      <li v-for="item in files" :key="item.path" class="file-row">
        <button type="button" class="file-open" :title="item.path" @click="openFile(item.path)">
          <AppIcon :name="actionIcon(item.action)" :size="14" />
          <span class="file-copy">
            <strong>{{ fileName(item.path) }}</strong>
            <small>{{ item.path }}</small>
          </span>
          <span class="action-pill">{{ actionLabel(item.action) }}</span>
        </button>
        <div class="file-actions">
          <button
            type="button"
            class="file-btn accept"
            :disabled="busy"
            :title="t('editor.accept')"
            @click="acceptFile(item)"
          >
            {{ t('editor.accept') }}
          </button>
          <button
            type="button"
            class="file-btn reject"
            :disabled="busy"
            :title="t('editor.reject')"
            @click="rejectFile(item)"
          >
            {{ t('editor.reject') }}
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.run-review {
  margin: 8px 0 2px;
  border: 1px solid color-mix(in srgb, var(--danger) 28%, var(--border));
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--danger) 7%, var(--panel-bg));
  overflow: hidden;
}
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
}
.copy {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-h);
  cursor: pointer;
  text-align: left;
}
.copy em {
  font-style: normal;
  font-weight: 500;
  font-size: 11.5px;
  color: var(--text-muted);
}
.chevron { flex-shrink: 0; color: var(--text-muted); }
.actions { display: flex; gap: 6px; }
.run-btn {
  height: 26px;
  padding: 0 10px;
  border-radius: var(--ghost-btn-radius);
  border: 1px solid var(--border);
  background: var(--panel-bg);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.run-btn.accept { color: #059669; }
.run-btn.reject {
  color: #fff;
  background: var(--danger);
  border-color: var(--danger);
}
.run-btn:disabled,
.file-btn:disabled { opacity: 0.6; cursor: wait; }

.file-list {
  list-style: none;
  margin: 0;
  padding: 0 8px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-top: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
}
.file-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 6px 6px 8px;
  border-radius: calc(var(--radius-md) - 2px);
}
.file-row:hover { background: color-mix(in srgb, var(--text-h) 5%, transparent); }
.file-open {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-h);
  cursor: pointer;
  text-align: left;
}
.file-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 1px;
}
.file-copy strong {
  font-size: 12.5px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-copy small {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--mono, ui-monospace, monospace);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.action-pill {
  flex-shrink: 0;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  color: var(--text-secondary);
  border: 1px solid var(--border);
}
.file-actions { display: flex; gap: 4px; flex-shrink: 0; }
.file-btn {
  height: 24px;
  padding: 0 8px;
  border-radius: var(--ghost-btn-radius);
  border: 1px solid var(--border);
  background: var(--panel-bg);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.file-btn.accept { color: #059669; }
.file-btn.reject { color: var(--danger); }
</style>
