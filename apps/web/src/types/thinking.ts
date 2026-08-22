export type ThinkingLevel = 'off' | 'low' | 'medium' | 'high'

export const THINKING_LEVELS: { value: ThinkingLevel; label: string; description: string }[] = [
  { value: 'off', label: '关闭', description: '不输出思考过程' },
  { value: 'low', label: '轻量', description: '必要时简短推理' },
  { value: 'medium', label: '标准', description: '平衡速度与推理深度' },
  { value: 'high', label: '深度', description: '充分推理后再行动（Codex xhigh）' },
]

export function loadThinkingLevel(): ThinkingLevel {
  const saved = localStorage.getItem('ca.thinking_level')
  if (saved === 'off' || saved === 'low' || saved === 'medium' || saved === 'high') return saved
  return localStorage.getItem('ca.thinking') === '1' ? 'medium' : 'off'
}

export function isThinkingEnabled(level: ThinkingLevel): boolean {
  return level !== 'off'
}
