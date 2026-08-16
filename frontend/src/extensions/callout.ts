import { mergeAttributes, Node } from '@tiptap/core'

export const Callout = Node.create({
  name: 'callout',
  group: 'block',
  content: 'block+',
  defining: true,
  addAttributes() {
    return {
      variant: { default: 'info' },
      title: { default: '设计提示' },
    }
  },
  parseHTML() {
    return [{ tag: 'aside[data-node-type="callout"]' }]
  },
  renderHTML({ HTMLAttributes }) {
    return ['aside', mergeAttributes(HTMLAttributes, {
      'data-node-type': 'callout',
      'data-title': HTMLAttributes.title,
      class: `studio-callout studio-callout-${HTMLAttributes.variant}`,
    }), 0]
  },
})
