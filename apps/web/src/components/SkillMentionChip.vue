<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import { useAppStore } from '@/stores/app'

const props = defineProps<{
  name: string
  removable?: boolean
}>()

const emit = defineEmits<{
  remove: []
}>()

const { t } = useI18n()
const store = useAppStore()

function openSkillPage() {
  if (!props.name) return
  store.openSkill(props.name)
}
</script>

<template>
  <span class="skill-mention-chip" :class="{ readonly: !removable }">
    <span
      class="skill-mention-body"
      role="button"
      tabindex="0"
      @click.stop="openSkillPage"
      @keydown.enter.prevent="openSkillPage"
    >
      <AppIcon name="book" :size="12" />
      <span class="skill-mention-name">{{ name }}</span>
    </span>
    <button
      v-if="removable"
      type="button"
      class="skill-mention-remove"
      :title="t('common.remove')"
      @mousedown.prevent
      @click.stop="emit('remove')"
    >
      <AppIcon name="close" :size="10" />
    </button>
  </span>
</template>

<style scoped>
.skill-mention-chip.readonly {
  padding: 1px 7px 1px 5px;
  border-radius: 5px;
  vertical-align: middle;
  margin: 0 2px;
}
.skill-mention-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin: 0 2px 0 0;
  padding: 2px 2px 2px 8px;
  border-radius: 6px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 12px;
  font-family: var(--mono);
  font-weight: 500;
  white-space: nowrap;
  vertical-align: baseline;
  user-select: none;
  line-height: 1.4;
}
.skill-mention-body {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  cursor: pointer;
}
.skill-mention-body:hover {
  opacity: 0.85;
}
.skill-mention-name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.skill-mention-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--primary);
  cursor: pointer;
  opacity: 0.65;
  flex-shrink: 0;
}
.skill-mention-remove:hover {
  opacity: 1;
  background: var(--border);
}
</style>
