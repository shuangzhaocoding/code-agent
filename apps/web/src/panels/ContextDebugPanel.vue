<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/http'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import { formatRelativeTime } from '@/utils/relativeTime'

type RuleItem = {
  path: string
  title?: string
  pinned?: boolean
  root?: boolean
  chars?: number
  reason?: string
  injected?: boolean
}

type SkillItem = {
  name: string
  description?: string
  source?: string
  path?: string
  reason?: string
  chars?: number
}

type MemoryItem = {
  id?: string
  kind: string
  subject: string
  pinned?: boolean
  statement?: string
}

type ContextDebug = {
  mode?: string
  thinking_level?: string
  rules?: {
    injected?: RuleItem[]
    omitted?: RuleItem[]
    truncated?: boolean
    max_chars?: number
  }
  skills_catalog?: SkillItem[]
  active_skill?: SkillItem | null
  skills_loaded?: SkillItem[]
  memories?: MemoryItem[]
  conversation_summary?: { present?: boolean; chars?: number }
  window?: {
    message_count?: number
    token_estimate?: number
    needs_compress?: boolean
  }
}

type RunDebugRow = {
  run_id: string
  status: string
  mode: string
  started_at?: string | null
  context_debug: ContextDebug
}

const { t } = useI18n()
const store = useAppStore()
const loading = ref(false)
const error = ref('')
const runs = ref<RunDebugRow[]>([])
const selectedId = ref<string | null>(null)
const showCatalog = ref(false)

const selected = computed(() => runs.value.find((r) => r.run_id === selectedId.value) || runs.value[0] || null)
const debug = computed(() => selected.value?.context_debug || null)

async function load() {
  const cid = store.conversationId
  if (!cid) {
    runs.value = []
    selectedId.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    const data = await api<{ runs: RunDebugRow[] }>(`/api/conversations/${cid}/context-debug`)
    runs.value = data.runs || []
    if (store.activeRunId && runs.value.some((r) => r.run_id === store.activeRunId)) {
      selectedId.value = store.activeRunId
    } else if (!selectedId.value || !runs.value.some((r) => r.run_id === selectedId.value)) {
      selectedId.value = runs.value[0]?.run_id || null
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

function sourceLabel(source?: string) {
  if (source === 'user_mention') return t('contextDebug.sourceMention')
  if (source === 'load_skill') return t('contextDebug.sourceLoadSkill')
  return source || '—'
}

watch(
  () => [store.conversationId, store.activeRunId, store.runStatus] as const,
  () => void load(),
  { immediate: true },
)
onMounted(() => void load())
</script>

<template>
  <div class="panel-shell context-debug-panel">
    <div class="panel-body">
      <header class="page-head">
        <div>
          <h1 class="page-title">{{ t('contextDebug.title') }}</h1>
          <p class="page-lead">{{ t('contextDebug.hint') }}</p>
        </div>
        <button type="button" class="btn btn-ghost" :disabled="loading" @click="load">
          <AppIcon name="refresh" :size="16" :stroke-width="1.75" />
          {{ t('common.refresh') }}
        </button>
      </header>

      <p v-if="!store.conversationId" class="empty">{{ t('contextDebug.noConversation') }}</p>
      <p v-else-if="error" class="banner err">{{ error }}</p>
      <div v-else-if="loading && !runs.length" class="empty">
        <AppIcon name="loader" :size="28" />
        <p>{{ t('common.loading') }}</p>
      </div>
      <div v-else-if="!runs.length" class="empty">
        <AppIcon name="eye" :size="28" />
        <p>{{ t('contextDebug.empty') }}</p>
        <small>{{ t('contextDebug.emptyHint') }}</small>
      </div>

      <template v-else>
        <div class="run-tabs">
          <button
            v-for="row in runs"
            :key="row.run_id"
            type="button"
            class="run-tab"
            :class="{ on: selected?.run_id === row.run_id }"
            @click="selectedId = row.run_id"
          >
            <span class="run-status" :data-status="row.status">{{ row.status }}</span>
            <span>{{ row.started_at ? formatRelativeTime(row.started_at) : row.run_id.slice(0, 8) }}</span>
          </button>
        </div>

        <section v-if="debug" class="summary-grid">
          <div class="stat">
            <span>{{ t('contextDebug.mode') }}</span>
            <strong>{{ debug.mode || '—' }}</strong>
          </div>
          <div class="stat">
            <span>{{ t('contextDebug.thinking') }}</span>
            <strong>{{ debug.thinking_level || 'off' }}</strong>
          </div>
          <div class="stat">
            <span>{{ t('contextDebug.tokens') }}</span>
            <strong>~{{ debug.window?.token_estimate || 0 }}</strong>
          </div>
          <div class="stat">
            <span>{{ t('contextDebug.window') }}</span>
            <strong>{{ debug.window?.message_count || 0 }}</strong>
          </div>
        </section>

        <section class="block">
          <h2>
            <AppIcon name="book" :size="16" />
            {{ t('contextDebug.rulesTitle') }}
            <span class="count">{{ debug?.rules?.injected?.length || 0 }}</span>
            <span v-if="debug?.rules?.truncated" class="pill warn">{{ t('contextDebug.truncated') }}</span>
          </h2>
          <p class="lead">{{ t('contextDebug.rulesLead') }}</p>
          <article v-for="rule in debug?.rules?.injected || []" :key="rule.path" class="row ok">
            <div>
              <strong>{{ rule.title || rule.path }}</strong>
              <code>{{ rule.path }}</code>
            </div>
            <div class="meta">
              <span v-if="rule.pinned" class="pill">{{ t('memory.pinned') }}</span>
              <span class="muted">{{ rule.chars || 0 }} chars</span>
            </div>
          </article>
          <article v-for="rule in debug?.rules?.omitted || []" :key="'o-' + rule.path" class="row off">
            <div>
              <strong>{{ rule.title || rule.path }}</strong>
              <code>{{ rule.path }}</code>
            </div>
            <div class="meta">
              <span class="pill off">{{ rule.reason || 'omitted' }}</span>
            </div>
          </article>
          <p v-if="!(debug?.rules?.injected?.length || debug?.rules?.omitted?.length)" class="muted">
            {{ t('contextDebug.noRules') }}
          </p>
        </section>

        <section class="block">
          <h2>
            <AppIcon name="sparkles" :size="16" />
            {{ t('contextDebug.skillsTitle') }}
          </h2>
          <p class="lead">{{ t('contextDebug.skillsLead') }}</p>

          <article v-if="debug?.active_skill" class="row ok highlight">
            <div>
              <strong>@{{ debug.active_skill.name }}</strong>
              <p class="reason">{{ debug.active_skill.reason || sourceLabel(debug.active_skill.source) }}</p>
            </div>
            <div class="meta">
              <span class="pill on">{{ sourceLabel(debug.active_skill.source) }}</span>
              <span class="muted">{{ debug.active_skill.chars || 0 }} chars</span>
            </div>
          </article>

          <article
            v-for="skill in debug?.skills_loaded || []"
            :key="'loaded-' + skill.name"
            class="row ok"
          >
            <div>
              <strong>{{ skill.name }}</strong>
              <p class="reason">{{ skill.reason || sourceLabel(skill.source) }}</p>
            </div>
            <div class="meta">
              <span class="pill">{{ sourceLabel(skill.source) }}</span>
            </div>
          </article>

          <p v-if="!debug?.active_skill && !(debug?.skills_loaded || []).length" class="muted">
            {{ t('contextDebug.noActiveSkill') }}
          </p>

          <button type="button" class="link-btn" @click="showCatalog = !showCatalog">
            {{ showCatalog ? t('contextDebug.hideCatalog') : t('contextDebug.showCatalog', { n: debug?.skills_catalog?.length || 0 }) }}
          </button>
          <div v-if="showCatalog" class="catalog">
            <article v-for="skill in debug?.skills_catalog || []" :key="skill.name" class="row soft">
              <div>
                <strong>{{ skill.name }}</strong>
                <p class="reason">{{ skill.description }}</p>
              </div>
              <span class="muted">{{ skill.source }}</span>
            </article>
          </div>
        </section>

        <section class="block">
          <h2>
            <AppIcon name="memory" :size="16" />
            {{ t('contextDebug.memoriesTitle') }}
            <span class="count">{{ debug?.memories?.length || 0 }}</span>
          </h2>
          <article v-for="mem in debug?.memories || []" :key="mem.id || mem.subject" class="row soft">
            <div>
              <strong>{{ mem.subject }}</strong>
              <p class="reason">{{ mem.statement }}</p>
            </div>
            <div class="meta">
              <span class="pill">{{ mem.kind }}</span>
              <span v-if="mem.pinned" class="pill">{{ t('memory.pinned') }}</span>
            </div>
          </article>
          <p v-if="!(debug?.memories || []).length" class="muted">{{ t('contextDebug.noMemories') }}</p>
        </section>

        <section class="block">
          <h2>
            <AppIcon name="chat" :size="16" />
            {{ t('contextDebug.summaryTitle') }}
          </h2>
          <p class="muted">
            <template v-if="debug?.conversation_summary?.present">
              {{ t('contextDebug.summaryPresent', { n: debug.conversation_summary.chars || 0 }) }}
            </template>
            <template v-else>{{ t('contextDebug.summaryAbsent') }}</template>
            <template v-if="debug?.window?.needs_compress"> · {{ t('contextDebug.needsCompress') }}</template>
          </p>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.context-debug-panel {
  height: 100%;
  min-height: 0;
}
.panel-body {
  height: 100%;
  overflow: auto;
  padding: 16px 18px 28px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.page-title {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
}
.page-lead {
  margin: 4px 0 0;
  color: var(--ca-muted, #8b93a7);
  font-size: 12.5px;
  line-height: 1.45;
}
.run-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.run-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--ca-border, #2a3142);
  background: transparent;
  color: inherit;
  border-radius: 8px;
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
}
.run-tab.on {
  border-color: var(--ca-accent, #f59e0b);
  background: color-mix(in srgb, var(--ca-accent, #f59e0b) 12%, transparent);
}
.run-status {
  text-transform: uppercase;
  font-size: 10px;
  opacity: 0.75;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.stat {
  border: 1px solid var(--ca-border, #2a3142);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stat span {
  font-size: 11px;
  color: var(--ca-muted, #8b93a7);
}
.stat strong {
  font-size: 14px;
}
.block {
  border: 1px solid var(--ca-border, #2a3142);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.block h2 {
  margin: 0;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.count {
  font-weight: 500;
  color: var(--ca-muted, #8b93a7);
}
.lead {
  margin: 0;
  font-size: 12px;
  color: var(--ca-muted, #8b93a7);
}
.row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--ca-fg, #fff) 3%, transparent);
}
.row.highlight {
  outline: 1px solid color-mix(in srgb, var(--ca-accent, #f59e0b) 45%, transparent);
}
.row.off {
  opacity: 0.65;
}
.row strong {
  display: block;
  font-size: 13px;
}
.row code {
  font-size: 11px;
  color: var(--ca-muted, #8b93a7);
}
.reason {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--ca-muted, #8b93a7);
  line-height: 1.4;
}
.meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}
.pill {
  font-size: 10px;
  border-radius: 999px;
  padding: 2px 7px;
  background: color-mix(in srgb, var(--ca-fg, #fff) 8%, transparent);
}
.pill.on,
.pill.warn {
  background: color-mix(in srgb, var(--ca-accent, #f59e0b) 22%, transparent);
}
.pill.off {
  background: color-mix(in srgb, #ef4444 18%, transparent);
}
.muted {
  color: var(--ca-muted, #8b93a7);
  font-size: 12px;
}
.link-btn {
  align-self: flex-start;
  border: 0;
  background: transparent;
  color: var(--ca-accent, #f59e0b);
  cursor: pointer;
  font-size: 12px;
  padding: 0;
}
.catalog {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 220px;
  overflow: auto;
}
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 48px 16px;
  color: var(--ca-muted, #8b93a7);
  text-align: center;
}
.banner.err {
  color: #f87171;
  font-size: 13px;
}
@media (max-width: 720px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
