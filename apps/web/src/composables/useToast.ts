import { computed, ref } from 'vue'

export type ToastKind = 'info' | 'success' | 'error' | 'warning'

export type ToastItem = {
  id: string
  kind: ToastKind
  message: string
  duration: number
}

const toasts = ref<ToastItem[]>([])
let seq = 0
const timers = new Map<string, ReturnType<typeof setTimeout>>()

function dismiss(id: string) {
  const timer = timers.get(id)
  if (timer) {
    clearTimeout(timer)
    timers.delete(id)
  }
  toasts.value = toasts.value.filter((item) => item.id !== id)
}

function push(message: string, kind: ToastKind = 'info', duration = 3600) {
  const text = (message || '').trim()
  if (!text) return
  const id = `toast-${++seq}`
  const item: ToastItem = { id, kind, message: text, duration }
  toasts.value = [...toasts.value.filter((t) => t.message !== text || t.kind !== kind), item].slice(-4)
  if (duration > 0) {
    timers.set(
      id,
      setTimeout(() => {
        timers.delete(id)
        dismiss(id)
      }, duration),
    )
  }
  return id
}

export function useToast() {
  return {
    toasts: computed(() => toasts.value),
    push,
    info: (message: string, duration?: number) => push(message, 'info', duration),
    success: (message: string, duration?: number) => push(message, 'success', duration),
    error: (message: string, duration?: number) => push(message, 'error', duration ?? 5200),
    warning: (message: string, duration?: number) => push(message, 'warning', duration),
    dismiss,
  }
}
