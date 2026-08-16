import { afterEach, describe, expect, it, vi } from 'vitest'

import { createStudioEditor } from './editor'
import { defaultSlashCommands, setupSlashMenu } from './slash-menu'

const editors: ReturnType<typeof createStudioEditor>[] = []

function mount() {
  const host = document.createElement('div')
  const surface = document.createElement('div')
  host.append(surface)
  document.body.append(host)
  const editor = createStudioEditor({ element: surface })
  editors.push(editor)
  const onImage = vi.fn()
  const menu = setupSlashMenu(host, editor, defaultSlashCommands({ onImage }))
  return { editor, host, menu, onImage }
}

afterEach(() => {
  editors.splice(0).forEach((editor) => editor.destroy())
  document.body.replaceChildren()
})

describe('slash menu', () => {
  it('opens from the slash key and filters searchable insertion commands', () => {
    const { editor, host } = mount()

    editor.view.dom.dispatchEvent(new KeyboardEvent('keydown', {
      key: '/',
      bubbles: true,
      cancelable: true,
    }))
    const dialog = host.querySelector<HTMLElement>('[role="dialog"]')
    const input = host.querySelector<HTMLInputElement>('input[type="search"]')
    expect(dialog?.hidden).toBe(false)
    expect(document.activeElement).toBe(input)

    if (!input) throw new Error('search input missing')
    input.value = '表格'
    input.dispatchEvent(new InputEvent('input', { bubbles: true }))
    const options = host.querySelectorAll<HTMLButtonElement>('[role="option"]')
    expect(options).toHaveLength(1)
    expect(options[0]?.textContent).toContain('表格')
    options[0]?.click()
    expect(editor.getJSON().content?.some((node) => node.type === 'table')).toBe(true)
  })

  it('does not open while a Chinese input method is composing', () => {
    const { editor, host } = mount()

    editor.view.dom.dispatchEvent(new KeyboardEvent('keydown', {
      key: '/',
      isComposing: true,
      bubbles: true,
      cancelable: true,
    }))

    expect(host.querySelector<HTMLElement>('[role="dialog"]')?.hidden).toBe(true)
  })
})
