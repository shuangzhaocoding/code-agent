<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const store = useAppStore()

const visible = computed(() => {
  const s = store.streamConnection
  return s === 'reconnecting' || s === 'disconnected'
})

const title = computed(() => {
  if (store.streamConnection === 'reconnecting') return t('connection.reconnecting')
  if (store.streamConnection === 'disconnected') return t('connection.disconnected')
  return ''
})

const lead = computed(() => {
  if (store.streamConnection === 'reconnecting') return t('connection.reconnectingLead')
  if (store.streamConnection === 'disconnected') return t('connection.disconnectedLead')
  return ''
})

const iconName = computed(() =>
  store.streamConnection === 'disconnected' ? 'alert' : 'loader',
)

function retry() {
  store.reconnectActiveStream()
}
</script>

<template>
  <Transition name="conn-card">
    <aside
      v-if="visible"
      class="conn-card"
      :class="store.streamConnection"
      role="status"
      aria-live="polite"
    >
      <div class="conn-card-main">
        <span class="conn-glyph" aria-hidden="true">
          <span class="conn-glyph-icon" :class="{ spin: store.streamConnection === 'reconnecting' }">
            <AppIcon :name="iconName" :size="14" :stroke-width="1.75" />
          </span>
        </span>
        <div class="conn-copy">
          <strong>{{ title }}</strong>
          <p>{{ lead }}</p>
        </div>
        <button
          v-if="store.streamConnection === 'disconnected'"
          type="button"
          class="btn conn-retry"
          @click="retry"
        >
          {{ t('connection.retry') }}
        </button>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.conn-card {
  margin: 4px 2px 6px;
  border: 1px solid color-mix(in srgb, #d97706 30%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, #d97706 7%, var(--panel-bg));
  overflow: hidden;
}
.conn-card.disconnected {
  border-color: color-mix(in srgb, var(--danger) 30%, var(--border));
  background: color-mix(in srgb, var(--danger) 7%, var(--panel-bg));
}
.conn-card-main {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
}
.conn-glyph {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  flex-shrink: 0;
  color: #d97706;
  background: color-mix(in srgb, #d97706 14%, transparent);
}
.conn-card.disconnected .conn-glyph {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 12%, transparent);
}
.conn-glyph-icon {
  display: grid;
  place-items: center;
  line-height: 0;
}
.conn-glyph-icon.spin {
  animation: conn-spin 1.2s linear infinite;
}
.conn-copy {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.conn-copy strong {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
  line-height: 1.3;
}
.conn-copy p {
  margin: 0;
  font-size: 11px;
  line-height: 1.35;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conn-retry {
  flex-shrink: 0;
  padding: 2px 8px;
  font-size: 11px;
  height: 24px;
}
.conn-card-enter-active,
.conn-card-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}
.conn-card-enter-from,
.conn-card-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
@keyframes conn-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
