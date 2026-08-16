import { mergeAttributes, Node } from '@tiptap/core'

export const Equation = Node.create({
  name: 'equation',
  group: 'block',
  atom: true,
  selectable: true,
  addAttributes() {
    return { latex: { default: '' } }
  },
  parseHTML() {
    return [{ tag: 'div[data-node-type="equation"]' }]
  },
  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, {
      'data-node-type': 'equation',
      class: 'studio-equation',
    }), ['code', {}, HTMLAttributes.latex]]
  },
})
