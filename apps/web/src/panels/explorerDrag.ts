import type { InjectionKey, Ref } from 'vue'
import type { FsItem } from '@/stores/app'

export const FS_DRAG_MIME = 'application/x-code-agent-fs-item'

export type FsDragPayload = { path: string; is_dir: boolean }

export type ExplorerDragApi = {
  dragSrc: Ref<FsDragPayload | null>
  /** Hovered tree path for highlight; `''` means workspace root. */
  dropHoverPath: Ref<string | null>
  beginDrag: (item: FsItem) => void
  endDrag: () => void
  setDropHover: (path: string | null, destDir: string | null) => void
  canDropTo: (destDir: string) => boolean
  resolveDestDir: (item: FsItem) => string
  dropTo: (destDir: string) => Promise<void>
}

export const explorerDragKey: InjectionKey<ExplorerDragApi> = Symbol('explorerDrag')
