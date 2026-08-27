import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import SkillMentionView from '@/editor/SkillMentionView.vue'

export type SkillMentionAttrs = {
  name: string
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    skillMention: {
      insertSkillMention: (attrs: SkillMentionAttrs) => ReturnType
    }
  }
}

export const skillMentionExtension = Node.create({
  name: 'skillMention',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,
  draggable: false,

  addAttributes() {
    return {
      name: { default: null },
    }
  },

  parseHTML() {
    return [{ tag: 'span[data-skill-mention]' }]
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(HTMLAttributes, {
        'data-skill-mention': '',
        'data-name': node.attrs.name,
      }),
      node.attrs.name,
    ]
  },

  addNodeView() {
    return VueNodeViewRenderer(SkillMentionView)
  },

  addCommands() {
    return {
      insertSkillMention:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({
            type: this.name,
            attrs: { name: attrs.name },
          }),
    }
  },
})
