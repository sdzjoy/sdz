import { mergeAttributes, Node } from '@tiptap/core'

export const StandardReference = Node.create({
  name: 'standardReference',
  group: 'block',
  atom: true,
  selectable: true,
  addAttributes() {
    return { standardId: { default: null } }
  },
  parseHTML() {
    return [{ tag: 'aside[data-node-type="standard-reference"]' }]
  },
  renderHTML({ HTMLAttributes }) {
    return ['aside', mergeAttributes(HTMLAttributes, {
      'data-node-type': 'standard-reference',
      class: 'studio-reference-node',
    }), ['strong', {}, `规范记录 #${HTMLAttributes.standardId}`]]
  },
})
