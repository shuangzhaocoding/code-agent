import { defineAsyncComponent, type Component } from 'vue'

export const renderers: Record<string, Component> = {
  'assistant.markdown': defineAsyncComponent(() => import('./MarkdownBlock.vue')),
  'user.text': defineAsyncComponent(() => import('./MarkdownBlock.vue')),
  'assistant.thinking': defineAsyncComponent(() => import('./ThinkingBlock.vue')),
  'tool.call': defineAsyncComponent(() => import('./ToolCallBlock.vue')),
  'tool.result': defineAsyncComponent(() => import('./ToolCallBlock.vue')),
  'file.diff': defineAsyncComponent(() => import('./FileDiffBlock.vue')),
  'file.write': defineAsyncComponent(() => import('./FileDiffBlock.vue')),
  'file.delete': defineAsyncComponent(() => import('./FileDiffBlock.vue')),
  'file.read': defineAsyncComponent(() => import('./ToolCallBlock.vue')),
  'terminal': defineAsyncComponent(() => import('./TerminalReplayBlock.vue')),
  'skill.activated': defineAsyncComponent(() => import('./ToolCallBlock.vue')),
  'approval': defineAsyncComponent(() => import('./ApprovalBlock.vue')),
  error: defineAsyncComponent(() => import('./ErrorBlock.vue')),
}

const fallback = defineAsyncComponent(() => import('./GenericBlock.vue'))

export function rendererFor(type: string): Component {
  return renderers[type] || fallback
}
