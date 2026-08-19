<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { fetchContextUsage } from '@/services/contextUsageService'
import type { ContextUsageCategoryItem, ContextUsageData, PendingFilePayload } from '@/types/contextUsage'
import type { ThinkingLevel } from '@/types/thinking'

const props = defineProps<{
  open: boolean
  conversationId: string | null
  userContent: string
  thinkingLevel: ThinkingLevel
  thinking: boolean
  mode: string
  files: PendingFilePayload[]
}>()

const emit = defineEmits<{ close: [] }>()

const loading = ref(false)
const error = ref<string | null>(null)
const usage = ref<ContextUsageData | null>(null)
let abortController: AbortController | null = null

const CATEGORY_COLORS: Record<string, string> = {
  system_prompt: '#6366f1',
  memory_summary: '#8b5cf6',
  recent_messages: '#3b82f6',
  current_user: '#10b981',
  tools_schema: '#f59e0b',
  files: '#ec4899',
}

interface CategoryBarRow extends ContextUsageCategoryItem {
  color: string
  sharePercent: number
}

const categoryRows = computed((): CategoryBarRow[] => {
  if (!usage.value) return []
  const total = usage.value.totalEstimatedInput
  return [...usage.value.categories]
    .sort((a, b) => b.tokens - a.tokens)
    .map((item) => ({
      ...item,
      color: CATEGORY_COLORS[item.key] ?? '#94a3b8',
      sharePercent: total > 0 ? (item.tokens / total) * 100 : 0,
    }))
})

const stackedSegments = computed(() => {
  if (!usage.value || usage.value.totalEstimatedInput <= 0) return []
  return categoryRows.value.map((row) => ({
    key: row.key,
    label: row.label,
    color: row.color,
    widthPercent: Math.max(row.sharePercent, row.tokens > 0 ? 0.8 : 0),
  }))
})

const levelClass = computed(() => {
  const level = usage.value?.level ?? 'normal'
  if (level === 'warning') return 'is-warning'
  if (level === 'danger' || level === 'critical') return 'is-danger'
  return 'is-normal'
})

function formatPercent(value: number): string {
  return value.toFixed(2)
}

function formatTokenCount(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`
  if (abs >= 10_000) return `${(value / 1_000).toFixed(1)}K`
  return value.toLocaleString()
}

function levelLabel(level: string): string {
  if (level === 'warning') return '偏高'
  if (level === 'danger') return '过高'
  if (level === 'critical') return '临界'
  return '正常'
}

function handleClose() {
  if (loading.value) return
  emit('close')
}

async function loadUsage() {
  if (!props.conversationId) {
    error.value = '请先开始会话'
    return
  }

  abortController?.abort()
  abortController = new AbortController()
  loading.value = true
  error.value = null
  usage.value = null

  try {
    usage.value = await fetchContextUsage({
      conversationId: props.conversationId,
      userContent: props.userContent.trim(),
      thinkingLevel: props.thinkingLevel,
      thinking: props.thinking,
      mode: props.mode,
      files: props.files,
      signal: abortController.signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    error.value = err instanceof Error ? err.message : '获取上下文用量失败'
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (visible) => {
    if (!visible) {
      abortController?.abort()
      abortController = null
      loading.value = false
      error.value = null
      usage.value = null
      return
    }
    void loadUsage()
  },
)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="ctx-dialog" @click.self="handleClose">
      <div class="ctx-dialog__panel" role="dialog" aria-modal="true" aria-labelledby="ctx-dialog-title">
        <header class="ctx-dialog__header">
          <div class="ctx-dialog__header-main">
            <h3 id="ctx-dialog-title" class="ctx-dialog__title">上下文 Token 用量</h3>
            <span v-if="usage" class="ctx-dialog__level" :class="levelClass">
              {{ levelLabel(usage.level) }}
            </span>
          </div>
          <button type="button" class="ctx-dialog__close" aria-label="关闭" :disabled="loading" @click="handleClose">×</button>
        </header>

        <p v-if="!loading && !error && !userContent.trim()" class="ctx-dialog__hint">
          未输入内容时将仅估算历史上下文
        </p>

        <div v-if="loading" class="ctx-dialog__state">加载中…</div>

        <div v-else-if="error" class="ctx-dialog__state ctx-dialog__state--error">
          <p>{{ error }}</p>
          <button type="button" class="ctx-dialog__retry" @click="loadUsage">重试</button>
        </div>

        <div v-else-if="usage" class="ctx-dialog__body">
          <div class="ctx-dialog__hero">
            <p class="ctx-dialog__hero-label">预估输入总量</p>
            <p class="ctx-dialog__hero-value">
              {{ formatTokenCount(usage.totalEstimatedInput) }}
              <span class="ctx-dialog__hero-unit">tokens</span>
            </p>
          </div>

          <div class="ctx-dialog__metrics">
            <div class="ctx-dialog__metric">
              <div class="ctx-dialog__metric-head">
                <span>上下文上限</span>
                <span>{{ formatPercent(usage.usagePercent) }}%</span>
              </div>
              <div class="ctx-dialog__metric-bar">
                <div
                  class="ctx-dialog__metric-bar-fill"
                  :class="levelClass"
                  :style="{ width: `${Math.min(100, usage.usagePercent)}%` }"
                />
              </div>
              <p class="ctx-dialog__metric-foot">{{ formatTokenCount(usage.contextLimit) }}</p>
            </div>

            <div class="ctx-dialog__metric">
              <div class="ctx-dialog__metric-head">
                <span>建议上限</span>
                <span>{{ formatPercent(usage.recommendedUsagePercent) }}%</span>
              </div>
              <div class="ctx-dialog__metric-bar">
                <div
                  class="ctx-dialog__metric-bar-fill is-recommended"
                  :class="levelClass"
                  :style="{ width: `${Math.min(100, usage.recommendedUsagePercent)}%` }"
                />
              </div>
              <p class="ctx-dialog__metric-foot">{{ formatTokenCount(usage.recommendedLimit) }}</p>
            </div>
          </div>

          <section v-if="stackedSegments.length" class="ctx-dialog__chart" aria-label="分类用量">
            <h4 class="ctx-dialog__section-title">分类用量</h4>
            <div class="ctx-dialog__stacked-bar" role="img">
              <div
                v-for="segment in stackedSegments"
                :key="segment.key"
                class="ctx-dialog__stacked-segment"
                :style="{ width: `${segment.widthPercent}%`, backgroundColor: segment.color }"
                :title="`${segment.label}: ${segment.widthPercent.toFixed(1)}%`"
              />
            </div>
            <ul class="ctx-dialog__legend">
              <li v-for="row in categoryRows" :key="row.key" class="ctx-dialog__legend-item">
                <span class="ctx-dialog__legend-dot" :style="{ backgroundColor: row.color }" />
                <span class="ctx-dialog__legend-label">{{ row.label }}</span>
                <span class="ctx-dialog__legend-value">
                  {{ formatTokenCount(row.tokens) }}
                  <span class="ctx-dialog__legend-share">({{ formatPercent(row.sharePercent) }}%)</span>
                </span>
              </li>
            </ul>
          </section>

          <div v-if="usage.sessionStats" class="ctx-dialog__stats">
            <span class="ctx-dialog__stats-label">会话统计</span>
            <span class="ctx-dialog__stats-inline">数据库消息数 {{ usage.sessionStats.messagesInDb }}</span>
            <span class="ctx-dialog__stats-inline">窗口内消息数 {{ usage.sessionStats.messagesInWindow }}</span>
            <span class="ctx-dialog__stats-inline">已摘要消息 {{ usage.sessionStats.messagesSummarized }}</span>
            <span class="ctx-dialog__stats-inline">滑动窗口大小 {{ usage.sessionStats.slidingWindowSize }}</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ctx-dialog {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.35);
}

.ctx-dialog__panel {
  width: min(440px, 100%);
  padding: 16px;
  border: var(--border-width) solid var(--border);
  border-radius: 12px;
  background: var(--panel-bg);
  box-shadow: var(--shadow-md);
}

.ctx-dialog__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ctx-dialog__header-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.ctx-dialog__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-h);
}

.ctx-dialog__level {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
}

.ctx-dialog__level.is-normal {
  color: #047857;
  background: rgba(16, 185, 129, 0.14);
}

.ctx-dialog__level.is-warning {
  color: #b45309;
  background: rgba(245, 158, 11, 0.16);
}

.ctx-dialog__level.is-danger {
  color: var(--danger);
  background: rgba(217, 48, 37, 0.12);
}

.ctx-dialog__close {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}

.ctx-dialog__close:hover:not(:disabled) {
  background: var(--code-bg);
  color: var(--text-h);
}

.ctx-dialog__hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text);
  opacity: 0.75;
}

.ctx-dialog__state {
  margin-top: 12px;
  font-size: 13px;
  color: var(--text);
}

.ctx-dialog__state--error {
  color: var(--danger);
}

.ctx-dialog__state--error p {
  margin: 0;
}

.ctx-dialog__retry {
  margin-top: 8px;
  padding: 4px 10px;
  border: var(--border-width) solid var(--border);
  border-radius: 6px;
  background: var(--panel-bg);
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
}

.ctx-dialog__body {
  margin-top: 12px;
}

.ctx-dialog__hero {
  padding: 10px 12px;
  border: var(--border-width) solid var(--border);
  border-radius: 8px;
  background: var(--code-bg);
}

.ctx-dialog__hero-label {
  margin: 0;
  font-size: 11px;
  color: var(--text);
  opacity: 0.75;
}

.ctx-dialog__hero-value {
  margin: 2px 0 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-h);
  line-height: 1.2;
}

.ctx-dialog__hero-unit {
  margin-left: 4px;
  font-size: 12px;
  font-weight: 400;
  color: var(--text);
}

.ctx-dialog__metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}

.ctx-dialog__metric-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--text);
}

.ctx-dialog__metric-bar {
  height: 6px;
  margin-top: 6px;
  border-radius: 999px;
  background: var(--code-bg);
  overflow: hidden;
}

.ctx-dialog__metric-bar-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--primary);
}

.ctx-dialog__metric-bar-fill.is-recommended {
  background: #6366f1;
}

.ctx-dialog__metric-bar-fill.is-warning {
  background: #e6a700;
}

.ctx-dialog__metric-bar-fill.is-danger {
  background: var(--danger);
}

.ctx-dialog__metric-foot {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--text-muted);
}

.ctx-dialog__chart {
  margin-top: 14px;
}

.ctx-dialog__section-title {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}

.ctx-dialog__stacked-bar {
  display: flex;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--code-bg);
}

.ctx-dialog__stacked-segment + .ctx-dialog__stacked-segment {
  margin-left: 1px;
}

.ctx-dialog__legend {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.ctx-dialog__legend-item {
  display: grid;
  grid-template-columns: 10px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 4px 0;
  font-size: 12px;
}

.ctx-dialog__legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.ctx-dialog__legend-label {
  color: var(--text);
}

.ctx-dialog__legend-value {
  color: var(--text-h);
  font-variant-numeric: tabular-nums;
}

.ctx-dialog__legend-share {
  color: var(--text-muted);
}

.ctx-dialog__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: var(--border-width) solid var(--border);
  font-size: 11px;
  color: var(--text);
}

.ctx-dialog__stats-label {
  width: 100%;
  font-weight: 600;
  color: var(--text-h);
}

.ctx-dialog__stats-inline:not(:last-child)::after {
  content: '·';
  margin-left: 10px;
  color: var(--text-muted);
}
</style>
