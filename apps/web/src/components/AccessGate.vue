<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ApiError } from '@/api/http'
import BrandMark from '@/components/BrandMark.vue'

const { t } = useI18n()

const password = ref('')
const error = ref('')
const loading = ref(false)

const emit = defineEmits<{ unlocked: [] }>()

async function submit() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    await api<{ ok: boolean }>('/api/auth/unlock', {
      method: 'POST',
      body: JSON.stringify({ password: password.value }),
    })
    password.value = ''
    emit('unlocked')
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      error.value = t('accessGate.invalid')
    } else {
      error.value = err instanceof Error ? err.message : String(err)
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="access-gate" role="dialog" aria-modal="true" :aria-label="t('accessGate.title')">
    <form class="card" @submit.prevent="submit">
      <div class="brand">
        <BrandMark :size="36" />
        <h1>{{ t('accessGate.title') }}</h1>
        <p>{{ t('accessGate.lead') }}</p>
      </div>
      <label class="field">
        <span>{{ t('accessGate.password') }}</span>
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          autofocus
          :placeholder="t('accessGate.placeholder')"
        />
      </label>
      <p v-if="error" class="err">{{ error }}</p>
      <button type="submit" class="btn" :disabled="loading || !password.trim()">
        {{ loading ? t('common.loading') : t('accessGate.unlock') }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.access-gate {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: grid;
  place-items: center;
  background:
    radial-gradient(ellipse at 30% 20%, color-mix(in srgb, var(--ca-accent, #f59e0b) 18%, transparent), transparent 50%),
    var(--bg, #0f1115);
  padding: 24px;
}
.card {
  width: min(400px, 100%);
  border: 1px solid var(--border, #2a3142);
  border-radius: 16px;
  padding: 28px 24px;
  background: color-mix(in srgb, var(--panel-bg, #161a22) 92%, transparent);
  backdrop-filter: blur(12px);
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.brand {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.brand h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
}
.brand p {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted, #8b93a7);
  line-height: 1.45;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted, #8b93a7);
}
.field input {
  border: 1px solid var(--border, #2a3142);
  border-radius: 10px;
  background: var(--bg-muted, #0c0e12);
  color: inherit;
  padding: 10px 12px;
  font-size: 14px;
}
.err {
  margin: 0;
  color: #f87171;
  font-size: 13px;
}
.btn {
  border: 0;
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  background: color-mix(in srgb, var(--ca-accent, #f59e0b) 85%, #000);
  color: #111;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
