import { mergeAttributes, Node } from '@tiptap/core'

export const ParameterCard = Node.create({
  name: 'parameterCard',
  group: 'block',
  atom: true,
  selectable: true,
  addAttributes() {
    return {
      name: { default: '' },
      value: { default: '' },
      unit: { default: '' },
      note: { default: '' },
    }
  },
  parseHTML() {
    return [{ tag: 'div[data-node-type="parameter-card"]' }]
  },
  renderHTML({ HTMLAttributes }) {
    const displayValue = `${HTMLAttributes.value}${HTMLAttributes.unit ? ` ${HTMLAttributes.unit}` : ''}`
    return ['div', mergeAttributes(HTMLAttributes, {
      'data-node-type': 'parameter-card',
      class: 'studio-parameter-card',
    }),
    ['strong', {}, HTMLAttributes.name],
    ['span', {}, displayValue],
    ['small', {}, HTMLAttributes.note],
    ]
  },
})
