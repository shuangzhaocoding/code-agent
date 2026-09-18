<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import { useAppStore } from '@/stores/app'
import { panelTitle } from '@/i18n'

const { t } = useI18n()
const store = useAppStore()

const approvalCount = computed(() => store.pendingApprovals.length)
const reviewCount = computed(() => store.pendingReviews.length)
const visible = computed(() => approvalCount.value > 0 || reviewCount.value > 0)

function openAgent() {
  window.dispatchEvent(
    new CustomEvent('ca-open-panel', { detail: { id: 'agent' } }),
  )
}

function openReviews() {
  const path = store.pendingReviewPaths[0]
  if (path) {
    window.dispatchEvent(new CustomEvent('ca-open-review', { detail: { path } }))
    return
  }
  window.dispatchEvent(
    new CustomEvent('ca-open-panel', { detail: { id: 'editor', title: panelTitle('editor') } }),
  )
}
</script>

<template>
  <div v-if="visible" class="attention-bar" role="status" aria-live="polite">
    <span class="attention-lead">{{ t('attention.lead') }}</span>
    <button
      v-if="approvalCount"
      type="button"
      class="attention-chip is-approval"
      @click="openAgent"
    >
      <AppIcon name="alert" :size="13" />
      {{ t('attention.approvals', { n: approvalCount }) }}
    </button>
    <button
      v-if="reviewCount"
      type="button"
      class="attention-chip is-review"
      @click="openReviews"
    >
      <AppIcon name="file-edit" :size="13" />
      {{ t('attention.reviews', { n: reviewCount }) }}
    </button>
  </div>
</template>

<style scoped>
.attention-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: var(--border-width) solid var(--border);
  background: color-mix(in srgb, var(--primary) 7%, var(--panel-bg));
  flex-shrink: 0;
}
.attention-lead {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}
.attention-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  border: var(--border-width) solid var(--border);
  background: var(--panel-bg);
  color: var(--text-h);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.attention-chip:hover {
  border-color: var(--primary);
  color: var(--primary);
}
.attention-chip.is-approval {
  border-color: color-mix(in srgb, var(--danger) 40%, var(--border));
  color: var(--danger);
}
</style>
