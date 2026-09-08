<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const detailsOpen = ref(false)

const pending = computed(() => store.pendingApprovals)
const current = computed(() => pending.value[0] || null)
const extraCount = computed(() => Math.max(0, pending.value.length - 1))

function decide(allowed: boolean) {
  const item = current.value
  if (!item) return
  store.decideApproval(item.approvalId, allowed)
  detailsOpen.value = false
}
</script>

<template>
  <Transition name="approval-bar">
    <aside v-if="current" class="approval-bar" role="region" aria-label="需要确认的操作">
      <div class="bar-main">
        <span class="glyph" aria-hidden="true">
          <AppIcon name="alert" :size="16" :stroke-width="1.75" />
        </span>
        <div class="copy">
          <div class="title-row">
            <strong>需要确认</strong>
            <span class="tool">{{ current.tool }}</span>
            <span v-if="extraCount" class="badge">还有 {{ extraCount }} 项</span>
          </div>
          <p class="summary">{{ current.summary }}</p>
          <button
            v-if="current.details"
            type="button"
            class="details-toggle"
            :aria-expanded="detailsOpen"
            @click="detailsOpen = !detailsOpen"
          >
            {{ detailsOpen ? '收起详情' : '查看详情' }}
          </button>
          <pre v-if="detailsOpen && current.details" class="details">{{ current.details }}</pre>
        </div>
        <div class="actions">
          <button type="button" class="btn btn-ghost" @click="decide(false)">拒绝</button>
          <button type="button" class="btn btn-allow" @click="decide(true)">允许执行</button>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.approval-bar {
  margin: 0 0 10px;
  border: 1px solid color-mix(in srgb, var(--danger) 35%, var(--border));
  border-radius: 12px;
  background: color-mix(in srgb, var(--danger) 8%, var(--panel-bg));
  box-shadow: 0 8px 24px color-mix(in srgb, #000 8%, transparent);
  overflow: hidden;
}
.bar-main {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 12px 12px 14px;
}
.glyph {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 12%, transparent);
  flex-shrink: 0;
}
.copy {
  min-width: 0;
  flex: 1;
}
.title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  margin-bottom: 2px;
}
.title-row strong {
  font-size: 13px;
  font-weight: 650;
  color: var(--text-h);
}
.tool {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-muted);
}
.badge {
  font-size: 11px;
  color: var(--text-secondary);
  padding: 1px 6px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--text-muted) 12%, transparent);
}
.summary {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}
.details-toggle {
  margin-top: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.details-toggle:hover {
  color: var(--text-h);
}
.details {
  margin: 8px 0 0;
  max-height: 140px;
  overflow: auto;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  font-family: var(--mono);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
.actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
  padding-top: 2px;
}
.btn-allow {
  background: var(--danger);
  color: #fff;
  font-weight: 600;
}
.btn-allow:hover {
  opacity: 0.9;
}

@media (max-width: 720px) {
  .bar-main {
    flex-wrap: wrap;
  }
  .actions {
    width: 100%;
    justify-content: flex-end;
  }
}

.approval-bar-enter-active,
.approval-bar-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.approval-bar-enter-from,
.approval-bar-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>
