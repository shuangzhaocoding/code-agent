import type {
  ContextUsageCategoryItem,
  ContextUsageData,
  ContextUsageLevel,
  ContextUsageRequestParams,
  ContextUsageSessionStats,
} from '@/types/contextUsage'

function readNumber(record: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
  }
  return null
}

function readBoolean(record: Record<string, unknown>, ...keys: string[]): boolean {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'boolean') return value
  }
  return false
}

function readString(record: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string') return value
  }
  return ''
}

function parseCategoryItem(value: unknown): ContextUsageCategoryItem | null {
  if (!value || typeof value !== 'object') return null
  const record = value as Record<string, unknown>
  const key = readString(record, 'key')
  const tokens = readNumber(record, 'tokens')
  if (!key || tokens === null) return null
  return {
    key,
    label: readString(record, 'label') || key,
    tokens,
    chars: readNumber(record, 'chars') ?? 0,
  }
}

function parseSessionStats(value: unknown): ContextUsageSessionStats | null {
  if (!value || typeof value !== 'object') return null
  const record = value as Record<string, unknown>
  return {
    messagesInDb: readNumber(record, 'messages_in_db', 'messagesInDb') ?? 0,
    messagesInWindow: readNumber(record, 'messages_in_window', 'messagesInWindow') ?? 0,
    messagesSummarized: readNumber(record, 'messages_summarized', 'messagesSummarized') ?? 0,
    messagesOutsideWindow: readNumber(record, 'messages_outside_window', 'messagesOutsideWindow') ?? 0,
    summarizeTrigger: readNumber(record, 'summarize_trigger', 'summarizeTrigger') ?? 0,
    slidingWindowSize: readNumber(record, 'sliding_window_size', 'slidingWindowSize') ?? 0,
    memorySummaryChars: readNumber(record, 'memory_summary_chars', 'memorySummaryChars') ?? 0,
    needsSummarize: readBoolean(record, 'needs_summarize', 'needsSummarize'),
  }
}

function parseLevel(value: unknown): ContextUsageLevel {
  return typeof value === 'string' && value ? value : 'normal'
}

export function parseContextUsageData(data: unknown): ContextUsageData | null {
  if (!data || typeof data !== 'object') return null
  const record = data as Record<string, unknown>
  const totalEstimatedInput = readNumber(record, 'total_estimated_input', 'totalEstimatedInput')
  if (totalEstimatedInput === null) return null

  const categoriesRaw = record.categories
  const categories = Array.isArray(categoriesRaw)
    ? categoriesRaw.map(parseCategoryItem).filter((item): item is ContextUsageCategoryItem => item !== null)
    : []

  return {
    contextLimit: readNumber(record, 'context_limit', 'contextLimit') ?? 1_048_576,
    recommendedLimit: readNumber(record, 'recommended_limit', 'recommendedLimit') ?? 128_000,
    mode: readString(record, 'mode') || 'agent',
    thinking: readBoolean(record, 'thinking'),
    categories,
    totalEstimatedInput,
    sessionContextTokens:
      readNumber(record, 'session_context_tokens', 'sessionContextTokens') ?? totalEstimatedInput,
    peakInputTokens: readNumber(record, 'peak_input_tokens', 'peakInputTokens') ?? totalEstimatedInput,
    usagePercent: readNumber(record, 'usage_percent', 'usagePercent') ?? 0,
    recommendedUsagePercent:
      readNumber(record, 'recommended_usage_percent', 'recommendedUsagePercent') ?? 0,
    level: parseLevel(record.level),
    estimationMethod: readString(record, 'estimation_method', 'estimationMethod'),
    sessionStats: parseSessionStats(record.session_stats ?? record.sessionStats),
  }
}

export async function fetchContextUsage(params: ContextUsageRequestParams): Promise<ContextUsageData> {
  const { conversationId, userContent, thinking, mode, files, signal } = params
  if (!conversationId) throw new Error('请先开始会话')

  const response = await fetch(`/api/conversations/${conversationId}/context-usage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_content: userContent,
      thinking,
      mode,
      files: files ?? [],
    }),
    signal,
  })

  if (!response.ok) {
    const raw = await response.text()
    throw new Error(raw || '获取上下文用量失败')
  }

  const parsed = parseContextUsageData(await response.json())
  if (!parsed) throw new Error('上下文用量数据无效')
  return parsed
}
