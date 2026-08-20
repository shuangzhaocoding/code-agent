import type { Component } from 'vue'
import type { OpenFileKind } from '@/preview/classify'

export type PreviewProps = {
  path: string
  previewUrl: string
  mime?: string
  kind: OpenFileKind
  content?: string
  dirty?: boolean
}

export type PreviewAdapter = {
  id: OpenFileKind
  component: Component
}
