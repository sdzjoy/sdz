import { afterEach, describe, expect, it } from 'vitest'

import { createStudioEditor } from '../editor'
import { Callout } from './callout'
import { CloudResource } from './cloud-resource'
import { Equation } from './equation'
import { ParameterCard } from './parameter-card'
import { StandardReference } from './reference'

const editors: ReturnType<typeof createStudioEditor>[] = []

afterEach(() => {
  editors.splice(0).forEach((editor) => editor.destroy())
  document.body.replaceChildren()
})

describe('professional editor nodes', () => {
  it('persists source values and only object ids for database references', () => {
    const element = document.createElement('div')
    document.body.append(element)
    const editor = createStudioEditor({
      element,
      extensions: [Callout, Equation, StandardReference, ParameterCard, CloudResource],
    })
    editors.push(editor)

    editor.commands.setContent({
      type: 'doc',
      content: [
        {
          type: 'callout',
          attrs: { variant: 'warning', title: '校核提示' },
          content: [{ type: 'paragraph', content: [{ type: 'text', text: '注意冗余配置' }] }],
        },
        { type: 'equation', attrs: { latex: 'Q = mc\\Delta t' } },
        { type: 'standardReference', attrs: { standardId: 36 } },
        {
          type: 'parameterCard',
          attrs: { name: '供回水温差', value: '6', unit: '℃', note: '设计工况' },
        },
        { type: 'cloudResource', attrs: { resourceId: 52 } },
      ],
    })

    const content = editor.getJSON().content || []
    expect(content.slice(0, 5).map((node) => node.type)).toEqual([
      'callout',
      'equation',
      'standardReference',
      'parameterCard',
      'cloudResource',
    ])
    expect(content[2]?.attrs).toEqual({ standardId: 36 })
    expect(content[4]?.attrs).toEqual({ resourceId: 52 })
    expect(JSON.stringify(content[4])).not.toContain('share_url')
    expect(content[1]?.attrs?.latex).toBe('Q = mc\\Delta t')
  })
})
