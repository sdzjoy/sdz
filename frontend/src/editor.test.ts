import { afterEach, describe, expect, it, vi } from 'vitest'

import { createStudioEditor } from './editor'

const editors: ReturnType<typeof createStudioEditor>[] = []

function mountEditor(options: Partial<Parameters<typeof createStudioEditor>[0]> = {}) {
  const element = document.createElement('div')
  document.body.append(element)
  const editor = createStudioEditor({ element, ...options })
  editors.push(editor)
  return { editor, element }
}

afterEach(() => {
  editors.splice(0).forEach((editor) => editor.destroy())
  document.body.replaceChildren()
})

describe('createStudioEditor', () => {
  it('loads a JSON document into the editable surface', () => {
    const { editor, element } = mountEditor({
      content: {
        type: 'doc',
        content: [{ type: 'paragraph', content: [{ type: 'text', text: '数据中心暖通' }] }],
      },
    })

    expect(editor.getText()).toBe('数据中心暖通')
    expect(element.querySelector('[role="textbox"]')).not.toBeNull()
  })

  it('makes an empty editor visibly discoverable and clears the empty state after typing', () => {
    const { editor, element } = mountEditor()
    const textbox = element.querySelector<HTMLElement>('[role="textbox"]')

    expect(textbox?.dataset.empty).toBe('true')
    expect(textbox?.dataset.placeholder).toContain('开始写正文')

    editor.commands.setContent({
      type: 'doc',
      content: [{ type: 'paragraph', content: [{ type: 'text', text: '正文已经开始' }] }],
    })

    expect(textbox?.dataset.empty).toBe('false')
  })

  it('reports JSON updates to the caller', () => {
    const onChange = vi.fn()
    const { editor } = mountEditor({ onChange })

    editor.commands.setContent({
      type: 'doc',
      content: [{ type: 'paragraph', content: [{ type: 'text', text: '已更新' }] }],
    })

    expect(onChange).toHaveBeenCalled()
    expect(onChange.mock.lastCall?.[0]).toMatchObject({ type: 'doc' })
  })

  it('can start read-only and become editable later', () => {
    const { editor } = mountEditor({ editable: false })

    expect(editor.isEditable).toBe(false)
    editor.setEditable(true)
    expect(editor.isEditable).toBe(true)
  })

  it('releases its DOM event handlers when destroyed', () => {
    const { editor } = mountEditor()

    editor.destroy()

    expect(editor.isDestroyed).toBe(true)
  })
})
