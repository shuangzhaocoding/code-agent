export type ParamSpec = {
  supported?: boolean
  min?: number
  max?: number
  default?: number
  step?: number
}

export type ModelCapabilities = {
  temperature?: ParamSpec
  max_tokens?: ParamSpec
  top_p?: ParamSpec
  thinking?: { supported?: boolean; levels?: string[] }
  tools?: { supported?: boolean }
  vision?: { supported?: boolean }
}

export type ModelParams = {
  temperature?: number
  max_tokens?: number
  top_p?: number
}

export type ModelAvailability = {
  ok?: boolean
  error?: string
  checked_at?: string
  latency_ms?: number
}

export type LlmModel = {
  id: string
  model_id: string
  display_name: string
  is_default?: boolean
  supports_tools?: boolean
  supports_vision?: boolean
  context_window?: number
  capabilities?: ModelCapabilities
  availability?: ModelAvailability | null
  params?: ModelParams
}

export type LlmProvider = {
  id: string
  name: string
  kind: string
  base_url: string
  api_key_masked?: string
  enabled?: boolean
  models?: LlmModel[]
}

export type LlmPreset = {
  kind: string
  name: string
  title: string
  base_url: string
  needs_key: boolean
}
