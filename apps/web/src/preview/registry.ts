import type { Component } from 'vue'
import type { OpenFileKind } from '@/preview/classify'
import type { PreviewAdapter } from '@/preview/types'
import ImagePreview from '@/preview/adapters/ImagePreview.vue'
import VideoPreview from '@/preview/adapters/VideoPreview.vue'
import HtmlPreview from '@/preview/adapters/HtmlPreview.vue'
import PdfPreview from '@/preview/adapters/PdfPreview.vue'
import DocxPreview from '@/preview/adapters/DocxPreview.vue'
import XlsxPreview from '@/preview/adapters/XlsxPreview.vue'
import PptxPreview from '@/preview/adapters/PptxPreview.vue'
import BinaryFallback from '@/preview/adapters/BinaryFallback.vue'

const adapters: PreviewAdapter[] = [
  { id: 'image', component: ImagePreview },
  { id: 'video', component: VideoPreview },
  { id: 'html', component: HtmlPreview },
  { id: 'pdf', component: PdfPreview },
  { id: 'docx', component: DocxPreview },
  { id: 'xlsx', component: XlsxPreview },
  { id: 'pptx', component: PptxPreview },
  { id: 'binary', component: BinaryFallback },
]

const byId = new Map(adapters.map((a) => [a.id, a]))

export function resolvePreviewAdapter(kind: OpenFileKind): Component | null {
  if (kind === 'text') return null
  return byId.get(kind)?.component || BinaryFallback
}

export function listPreviewAdapters(): PreviewAdapter[] {
  return adapters
}
