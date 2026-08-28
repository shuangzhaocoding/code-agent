<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'

const { t } = useI18n()
const store = useAppStore()

const bulkConfirm = ref<'accept' | 'reject' | null>(null)
const rootRef = ref<HTMLElement | null>(null)
const pendingCount = computed(() => store.pendingReviews.length)
const gitChangeCount = computed(() => Object.keys(store.gitChangedPaths).length)
const canReviewGit = computed(() => store.gitRepoOk && gitChangeCount.value > 0)
const visible = computed(() => pendingCount.value > 0 || canReviewGit.value)

function openBulkConfirm(kind: 'accept' | 'reject') {
  bulkConfirm.value = bulkConfirm.value === kind ? null : kind
}

function closeBulkConfirm() {
  bulkConfirm.value = null
}

async function confirmBulk() {
  const kind = bulkConfirm.value
  if (!kind) return
  bulkConfirm.value = null
  if (kind === 'accept') await store.acceptAllReviews()
  else await store.rejectAllReviews()
}

function reviewGitChanges() {
  if (!canReviewGit.value) return
  void store.send(t('chat.promptReviewText'))
}

function onDocClick(e: MouseEvent) {
  if (!bulkConfirm.value) return
  const root = rootRef.value
  if (root && !root.contains(e.target as Node)) closeBulkConfirm()
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') closeBulkConfirm()
}

watch(pendingCount, (n) => {
  if (!n) closeBulkConfirm()
})

onMounted(() => {
  document.addEventListener('mousedown', onDocClick)
  document.addEventListener('keydown', onKey)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocClick)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div
    v-if="visible"
    ref="rootRef"
    class="review-bulk"
    role="group"
    :aria-label="t('editor.reviewActionsAll')"
  >
    <button
      v-if="canReviewGit"
      type="button"
      class="bulk-btn is-review"
      :title="t('chat.promptReviewText')"
      @click="reviewGitChanges"
    >
      <AppIcon name="git" :size="14" :stroke-width="1.75" />
      <span>{{ t('chat.promptReviewLabel') }}</span>
    </button>
    <span v-if="canReviewGit && pendingCount" class="bulk-sep" aria-hidden="true" />
    <template v-if="pendingCount">
      <button
        type="button"
        class="bulk-btn is-reject"
        :class="{ 'is-active': bulkConfirm === 'reject' }"
        :title="t('editor.rejectAll')"
        @click="openBulkConfirm('reject')"
      >
        <AppIcon name="close-all" :size="14" :stroke-width="1.75" />
        <span>{{ t('editor.rejectAll') }}</span>
      </button>
      <button
        type="button"
        class="bulk-btn is-accept"
        :class="{ 'is-active': bulkConfirm === 'accept' }"
        :title="t('editor.acceptAll')"
        @click="openBulkConfirm('accept')"
      >
        <AppIcon name="check" :size="14" :stroke-width="1.75" />
        <span>{{ t('editor.acceptAll') }}</span>
      </button>
      <div
        v-if="bulkConfirm"
        class="bulk-confirm"
        :class="{ 'is-danger': bulkConfirm === 'reject' }"
        role="dialog"
        :aria-label="bulkConfirm === 'accept' ? t('confirm.acceptAllReviewsTitle') : t('confirm.rejectAllReviewsTitle')"
        @mousedown.stop
      >
        <span class="bulk-confirm-count">{{ pendingCount }}</span>
        <button
          type="button"
          class="ghost-icon-btn confirm-btn"
          :title="t('common.cancel')"
          :aria-label="t('common.cancel')"
          @click="closeBulkConfirm"
        >
          <AppIcon name="close" :size="14" :stroke-width="1.75" />
        </button>
        <button
          type="button"
          class="ghost-icon-btn confirm-btn"
          :class="bulkConfirm === 'reject' ? 'is-danger' : 'is-primary'"
          :title="t('confirm.confirm')"
          :aria-label="t('confirm.confirm')"
          @click="confirmBulk"
        >
          <AppIcon name="check" :size="14" :stroke-width="1.75" />
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.review-bulk {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
}
html[data-theme='dark'] .review-bulk {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}
.bulk-sep {
  width: 1px;
  height: 14px;
  background: var(--border);
  flex-shrink: 0;
}
.bulk-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 22px;
  padding: 0 6px;
  border: 0;
  border-radius: calc(var(--radius-md) - 2px);
  background: transparent;
  color: var(--text-h);
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.12s ease, color 0.12s ease;
}
.bulk-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text-h) 8%, transparent);
}
.bulk-btn.is-active {
  background: color-mix(in srgb, var(--text-h) 10%, transparent);
}
.bulk-btn.is-review {
  color: var(--text-h);
}
.bulk-btn.is-reject:hover,
.bulk-btn.is-reject.is-active {
  color: var(--danger);
}
.bulk-btn.is-accept {
  color: var(--primary);
}
.bulk-confirm {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  box-shadow: var(--dropdown-shadow);
}
.bulk-confirm.is-danger {
  border-color: color-mix(in srgb, var(--danger) 28%, var(--border));
}
.bulk-confirm-count {
  min-width: 14px;
  padding: 0 4px;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  color: var(--text-secondary);
  text-align: center;
}
.confirm-btn.is-primary {
  color: var(--primary);
}
.confirm-btn.is-danger {
  color: var(--danger);
}
</style>
