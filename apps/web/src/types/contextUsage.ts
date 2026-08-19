export type ContextUsageLevel = 'normal' | 'warning' | 'danger' | 'critical' | string

export interface ContextUsageCategoryItem {
  key: string
  label: string
  tokens: number
  chars: number
  modes?: string[]
}

export interface ContextUsageSessionStats {
  messagesInDb: number
  messagesInWindow: number
  messagesSummarized: number
  messagesOutsideWindow: number
  summarizeTrigger: number
  slidingWindowSize: number
  memorySummaryChars: number
  needsSummarize: boolean
}

export interface ContextUsageData {
  contextLimit: number
  recommendedLimit: number
  mode: string
  thinking: boolean
  categories: ContextUsageCategoryItem[]
  totalEstimatedInput: number
  sessionContextTokens: number
  peakInputTokens: number
  usagePercent: number
  recommendedUsagePercent: number
  level: ContextUsageLevel
  estimationMethod: string
  sessionStats: ContextUsageSessionStats | null
}

export interface PendingFilePayload {
  name: string
  url: string
  size: number
  type: string
}

export interface ContextUsageRequestParams {
  conversationId?: string | null
  userContent: string
  thinking: boolean
  mode?: string
  files?: PendingFilePayload[]
  signal?: AbortSignal
}
