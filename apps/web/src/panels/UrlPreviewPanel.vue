<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import { useUrlPreview } from '@/composables/useUrlPreview'
import { isHttpUrl, openExternalUrl } from '@/utils/openUrl'

const { t } = useI18n()
const {
  tabs,
  activeId,
  activeTab,
  addBlankPreviewTab,
  activatePreviewTab,
  closePreviewTab,
  navigatePreviewTab,
  reloadPreviewTab,
  markPreviewTabBlocked,
} = useUrlPreview()

const draft = ref('')
const addressEl = ref<HTMLInputElement | null>(null)
const tabsEl = ref<HTMLElement | null>(null)

const pageTabs = computed(() => tabs.value.filter((tab) => Boolean(tab.url)))
const activeUrl = computed(() => activeTab.value?.url || '')

watch(
  () => [activeId.value, activeTab.value?.url] as const,
  () => {
    draft.value = activeTab.value?.url || ''
  },
  { immediate: true },
)

function tabLabel(tab: { url: string; title: string }) {
  return tab.title || t('preview.untitled')
}

function focusAddress() {
  nextTick(() => addressEl.value?.focus())
}

function addTab() {
  addBlankPreviewTab()
  focusAddress()
}

function onAddressEnter() {
  const id = activeId.value
  if (!id) {
    addBlankPreviewTab()
  }
  const target = activeId.value
  if (!target) return
  if (!navigatePreviewTab(target, draft.value)) {
    draft.value = activeTab.value?.url || draft.value
  }
}

function onTabAux(id: string, e: MouseEvent) {
  if (e.button !== 1) return
  e.preventDefault()
  closePreviewTab(id)
}

function onTabWheel(e: WheelEvent) {
  const el = tabsEl.value
  if (!el) return
  if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return
  el.scrollLeft += e.deltaY
}

async function openInBrowser() {
  if (!activeUrl.value) return
  await openExternalUrl(activeUrl.value)
}

function reload() {
  if (!activeId.value) return
  reloadPreviewTab(activeId.value)
}
</script>

<template>
  <div class="panel-shell preview-shell">
    <header class="file-bar">
      <div ref="tabsEl" class="tabs" role="tablist" @wheel.prevent="onTabWheel">
        <div
          v-for="tab in tabs"
          :key="tab.id"
          role="tab"
          class="ftab"
          :class="{ active: tab.id === activeId }"
          :title="tab.url || t('preview.untitled')"
          :aria-selected="tab.id === activeId"
          tabindex="0"
          @click="activatePreviewTab(tab.id)"
          @keydown.enter.prevent="activatePreviewTab(tab.id)"
          @auxclick="onTabAux(tab.id, $event)"
        >
          <AppIcon name="globe" :size="14" :stroke-width="1.75" />
          <span class="name">{{ tabLabel(tab) }}</span>
          <button
            type="button"
            class="ghost-icon-btn ftab-close"
            :title="t('preview.closeTab')"
            @click.stop="closePreviewTab(tab.id)"
          >
            <AppIcon name="close" :size="12" :stroke-width="1.75" />
          </button>
        </div>
      </div>
      <div class="file-bar-tools">
        <button type="button" class="ghost-icon-btn" :title="t('preview.newTab')" @click="addTab">
          <AppIcon name="plus" :size="15" :stroke-width="1.75" />
        </button>
      </div>
    </header>

    <div class="addr-bar">
      <button
        type="button"
        class="ghost-icon-btn"
        :title="t('common.refresh')"
        :disabled="!activeUrl"
        @click="reload"
      >
        <AppIcon name="refresh" :size="15" :stroke-width="1.75" />
      </button>
      <input
        ref="addressEl"
        v-model="draft"
        class="addr-input"
        type="url"
        spellcheck="false"
        :placeholder="t('preview.addressPlaceholder')"
        @keydown.enter.prevent="onAddressEnter"
      />
      <button
        type="button"
        class="ghost-icon-btn"
        :title="t('chat.openInBrowser')"
        :disabled="!activeUrl"
        @click="openInBrowser"
      >
        <AppIcon name="globe" :size="15" :stroke-width="1.75" />
      </button>
    </div>

    <div class="host-wrap">
      <div v-if="!tabs.length" class="empty">
        <AppIcon name="globe" :size="28" />
        <p>{{ t('preview.empty') }}</p>
      </div>
      <template v-else>
        <p v-if="activeTab?.blocked" class="fallback">
          {{ t('chat.urlPreviewBlocked') }}
          <button type="button" class="fallback-open" @click="openInBrowser">{{ t('chat.openInBrowser') }}</button>
        </p>
        <iframe
          v-for="tab in pageTabs"
          v-show="tab.id === activeId && !tab.blocked"
          :key="`${tab.id}-${tab.frameKey}`"
          class="frame"
          :src="tab.url"
          sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-same-origin"
          referrerpolicy="no-referrer"
          @error="markPreviewTabBlocked(tab.id)"
        />
        <div v-if="activeTab && !activeTab.url" class="empty">
          <AppIcon name="globe" :size="28" />
          <p>{{ t('preview.addressPlaceholder') }}</p>
        </div>
      </template>
    </div>

    <p v-if="activeUrl && isHttpUrl(activeUrl) && !activeTab?.blocked" class="foot">{{ t('chat.urlPreviewHint') }}</p>
  </div>
</template>

<style scoped>
.preview-shell {
  background: var(--editor-bg);
}
.file-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding-right: 8px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--bg);
}
.tabs {
  flex: 1;
  min-width: 0;
  display: flex;
  overflow-x: auto;
  scrollbar-width: none;
}
.tabs::-webkit-scrollbar {
  display: none;
}
.ftab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 8px 0 12px;
  border: 0;
  border-right: var(--border-width) solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12.5px;
  max-width: 220px;
  flex-shrink: 0;
}
.ftab:hover {
  color: var(--text-h);
  opacity: var(--ghost-hover-opacity);
}
.ftab.active {
  background: var(--editor-bg);
  color: var(--text-h);
  opacity: 1;
  box-shadow: inset 0 -2px 0 var(--primary);
}
.ftab-close {
  opacity: 0;
  transition: opacity 0.15s ease;
}
.ftab:hover .ftab-close,
.ftab.active .ftab-close {
  opacity: var(--ghost-hover-opacity);
}
.ftab-close:hover {
  opacity: 1 !important;
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-bar-tools {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}
.addr-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 8px;
  border-bottom: var(--border-width) solid var(--border);
  background: var(--panel-bg);
}
.addr-input {
  flex: 1;
  min-width: 0;
  height: 26px;
  padding: 0 10px;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm, 6px);
  background: var(--surface);
  color: var(--text);
  font-size: 12px;
  font-family: var(--mono);
}
.addr-input:focus {
  outline: none;
  border-color: var(--primary);
}
.host-wrap {
  flex: 1;
  min-height: 0;
  position: relative;
  background: var(--surface);
}
.frame {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  background: var(--surface);
}
.empty,
.fallback {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin: 0;
  padding: 24px;
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
}
.fallback-open {
  border: 0;
  background: transparent;
  color: var(--primary);
  cursor: pointer;
  font: inherit;
  text-decoration: underline;
}
.foot {
  margin: 0;
  padding: 6px 12px;
  font-size: 11px;
  color: var(--text-muted);
  border-top: var(--border-width) solid var(--border);
  flex-shrink: 0;
}
</style>
