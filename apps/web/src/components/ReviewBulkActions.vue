<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'

const { t } = useI18n()
const store = useAppStore()

const gitChangeCount = computed(() => Object.keys(store.gitChangedPaths).length)
const canReviewGit = computed(() => store.gitRepoOk && gitChangeCount.value > 0)

function reviewGitChanges() {
  if (!canReviewGit.value) return
  void store.send(t('chat.promptReviewText'))
}
</script>

<template>
  <div
    v-if="canReviewGit"
    class="review-bulk"
    role="group"
    :aria-label="t('editor.reviewActionsAll')"
  >
    <button
      type="button"
      class="bulk-btn is-review"
      :title="t('chat.promptReviewText')"
      @click="reviewGitChanges"
    >
      <AppIcon name="git" :size="14" :stroke-width="1.75" />
      <span>{{ t('chat.promptReviewLabel') }}</span>
    </button>
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
.bulk-btn.is-review {
  color: var(--text-h);
}
</style>
