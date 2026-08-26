<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { SUPPORTED_LOCALES, setLocale, type LocaleId } from '@/i18n'

const { locale, t } = useI18n()

const options = computed(() =>
  SUPPORTED_LOCALES.map((item) => ({
    id: item.id,
    label: t(`language.${item.id}`),
  })),
)

function onChange(e: Event) {
  const value = (e.target as HTMLSelectElement).value
  if (SUPPORTED_LOCALES.some((item) => item.id === value)) setLocale(value as LocaleId)
}
</script>

<template>
  <label class="lang-select">
    <span class="lang-label">{{ t('language.label') }}</span>
    <select class="field-control lang-control" :value="locale" @change="onChange">
      <option v-for="item in options" :key="item.id" :value="item.id">{{ item.label }}</option>
    </select>
  </label>
</template>

<style scoped>
.lang-select {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.lang-label {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}
.lang-control {
  min-width: 128px;
  height: 30px;
  padding: 0 8px;
  font-size: 12px;
}
</style>
