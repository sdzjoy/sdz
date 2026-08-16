import { mergeAttributes, Node } from '@tiptap/core'

export const CloudResource = Node.create({
  name: 'cloudResource',
  group: 'block',
  atom: true,
  selectable: true,
  addAttributes() {
    return { resourceId: { default: null } }
  },
  parseHTML() {
    return [{ tag: 'aside[data-node-type="cloud-resource"]' }]
  },
  renderHTML({ HTMLAttributes }) {
    return ['aside', mergeAttributes(HTMLAttributes, {
      'data-node-type': 'cloud-resource',
      class: 'studio-cloud-resource-node',
    }), ['strong', {}, `网盘资源 #${HTMLAttributes.resourceId}`]]
  },
})
