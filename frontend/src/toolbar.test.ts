import { afterEach, describe, expect, it } from 'vitest'

import { createStudioEditor } from './editor'
import { setupToolbar } from './toolbar'

const editors: ReturnType<typeof createStudioEditor>[] = []

afterEach(() => {
  editors.splice(0).forEach((editor) => editor.destroy())
  document.body.replaceChildren()
})

describe('editor toolbar', () => {
  it('runs formatting commands and reflects active state', () => {
    const root = document.createElement('div')
    root.innerHTML = '<button type="button" data-command="heading-2">二级标题</button><div data-surface></div>'
    document.body.append(root)
    const editor = createStudioEditor({
      element: root.querySelector<HTMLElement>('[data-surface]')!,
      content: { type: 'doc', content: [{ type: 'paragraph' }] },
    })
    editors.push(editor)
    setupToolbar(root, editor)

    const button = root.querySelector<HTMLButtonElement>('[data-command="heading-2"]')!
    button.click()

    expect(editor.isActive('heading', { level: 2 })).toBe(true)
    expect(button.getAttribute('aria-pressed')).toBe('true')
  })
})
