<script setup lang="ts">
import AppIcon from '@/components/AppIcon.vue'
import { useToast } from '@/composables/useToast'

const { toasts, dismiss } = useToast()

function iconFor(kind: string) {
  if (kind === 'success') return 'check'
  if (kind === 'error') return 'close'
  if (kind === 'warning') return 'alert'
  return 'help'
}
</script>

<template>
  <Teleport to="body">
    <div class="app-toast-stack" aria-live="polite" aria-relevant="additions">
      <TransitionGroup name="app-toast">
        <div
          v-for="item in toasts"
          :key="item.id"
          class="app-toast"
          :class="item.kind"
          role="status"
        >
          <AppIcon :name="iconFor(item.kind)" :size="15" />
          <span class="app-toast-msg">{{ item.message }}</span>
          <button type="button" class="app-toast-close" aria-label="Dismiss" @click="dismiss(item.id)">
            <AppIcon name="close" :size="14" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.app-toast-stack {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 14000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(360px, calc(100vw - 24px));
  pointer-events: none;
}
.app-toast {
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-h);
  box-shadow: var(--dropdown-shadow);
  font-size: 13px;
  line-height: 1.4;
}
.app-toast.success {
  border-color: color-mix(in srgb, #059669 35%, var(--border));
  background: color-mix(in srgb, #10b981 10%, var(--surface));
}
.app-toast.error {
  border-color: color-mix(in srgb, var(--danger) 35%, var(--border));
  background: color-mix(in srgb, var(--danger) 8%, var(--surface));
}
.app-toast.warning {
  border-color: color-mix(in srgb, #d97706 35%, var(--border));
  background: color-mix(in srgb, #f59e0b 10%, var(--surface));
}
.app-toast-msg {
  flex: 1;
  min-width: 0;
  word-break: break-word;
}
.app-toast-close {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.app-toast-close:hover {
  color: var(--text-h);
  background: color-mix(in srgb, var(--text) 8%, transparent);
}
.app-toast-enter-active,
.app-toast-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.app-toast-enter-from,
.app-toast-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
