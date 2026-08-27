import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import FileMentionView from '@/editor/FileMentionView.vue'

export type FileMentionAttrs = {
  path: string
  name: string
  isDir?: boolean
  lineStart?: number | null
  lineEnd?: number | null
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    fileMention: {
      insertFileMention: (attrs: FileMentionAttrs) => ReturnType
    }
  }
}

export const fileMentionExtension = Node.create({
  name: 'fileMention',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,
  draggable: false,

  addAttributes() {
    return {
      path: { default: null },
      name: { default: null },
      isDir: { default: false },
      lineStart: { default: null },
      lineEnd: { default: null },
    }
  },

  parseHTML() {
    return [{ tag: 'span[data-file-mention]' }]
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(HTMLAttributes, {
        'data-file-mention': '',
        'data-path': node.attrs.path,
        'data-name': node.attrs.name,
        'data-is-dir': node.attrs.isDir ? '1' : '0',
        'data-line-start': node.attrs.lineStart ?? '',
        'data-line-end': node.attrs.lineEnd ?? '',
      }),
      node.attrs.name,
    ]
  },

  addNodeView() {
    return VueNodeViewRenderer(FileMentionView)
  },

  addCommands() {
    return {
      insertFileMention:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({
            type: this.name,
            attrs: {
              path: attrs.path,
              name: attrs.name,
              isDir: Boolean(attrs.isDir),
              lineStart: attrs.lineStart ?? null,
              lineEnd: attrs.lineEnd ?? null,
            },
          }),
    }
  },
})
