<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import FormSelect from '@/components/FormSelect.vue'
import { SUPPORTED_LOCALES, setLocale, type LocaleId } from '@/i18n'

const props = withDefaults(
  defineProps<{
    showLabel?: boolean
    compact?: boolean
  }>(),
  {
    showLabel: true,
    compact: false,
  },
)

const { locale, t } = useI18n()

const options = computed(() =>
  SUPPORTED_LOCALES.map((item) => ({
    value: item.id,
    label: t(`language.${item.id}`),
  })),
)

function onUpdate(value: string) {
  if (SUPPORTED_LOCALES.some((item) => item.id === value)) setLocale(value as LocaleId)
}
</script>

<template>
  <div class="lang-select" :class="{ compact }">
    <span v-if="showLabel" class="lang-label">{{ t('language.label') }}</span>
    <FormSelect
      class="lang-control"
      :class="{ compact }"
      :model-value="locale"
      :options="options"
      @update:model-value="onUpdate"
    />
  </div>
</template>

<style scoped>
.lang-select {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  width: 100%;
}
.lang-select.compact {
  width: auto;
}
.lang-label {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}
.lang-control {
  flex: 1;
  min-width: 0;
}
.lang-control.compact {
  flex: 0 1 auto;
  min-width: 128px;
}
</style>
