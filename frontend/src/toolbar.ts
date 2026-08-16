import type { Editor } from '@tiptap/core'
import BubbleMenu from '@tiptap/extension-bubble-menu'

function editLink(editor: Editor): void {
  const current = editor.getAttributes('link').href as string | undefined
  const value = window.prompt('输入链接地址；留空可移除链接', current || 'https://')
  if (value === null) return
  if (!value.trim()) editor.chain().focus().extendMarkRange('link').unsetLink().run()
  else editor.chain().focus().extendMarkRange('link').setLink({ href: value.trim() }).run()
}

export function createToolbarExtensions(element: HTMLElement) {
  return [
    BubbleMenu.configure({
      element,
      updateDelay: 100,
      shouldShow: ({ editor, from, to }) => (
        editor.isEditable && from !== to && !editor.isActive('image')
      ),
    }),
  ]
}

export function setupToolbar(root: HTMLElement, editor: Editor): () => void {
  const commands: Record<string, () => void> = {
    paragraph: () => editor.chain().focus().setParagraph().run(),
    'heading-2': () => editor.chain().focus().toggleHeading({ level: 2 }).run(),
    'heading-3': () => editor.chain().focus().toggleHeading({ level: 3 }).run(),
    bold: () => editor.chain().focus().toggleBold().run(),
    italic: () => editor.chain().focus().toggleItalic().run(),
    strike: () => editor.chain().focus().toggleStrike().run(),
    link: () => editLink(editor),
    'bullet-list': () => editor.chain().focus().toggleBulletList().run(),
    'ordered-list': () => editor.chain().focus().toggleOrderedList().run(),
    blockquote: () => editor.chain().focus().toggleBlockquote().run(),
    'code-block': () => editor.chain().focus().toggleCodeBlock().run(),
    table: () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
    divider: () => editor.chain().focus().setHorizontalRule().run(),
    clear: () => editor.chain().focus().unsetAllMarks().clearNodes().run(),
    undo: () => editor.chain().focus().undo().run(),
    redo: () => editor.chain().focus().redo().run(),
  }
  const buttons = Array.from(root.querySelectorAll<HTMLButtonElement>('[data-command]'))
  for (const button of buttons) {
    button.addEventListener('click', () => commands[button.dataset.command || '']?.())
  }

  const activeChecks: Record<string, () => boolean> = {
    paragraph: () => editor.isActive('paragraph'),
    'heading-2': () => editor.isActive('heading', { level: 2 }),
    'heading-3': () => editor.isActive('heading', { level: 3 }),
    bold: () => editor.isActive('bold'),
    italic: () => editor.isActive('italic'),
    strike: () => editor.isActive('strike'),
    link: () => editor.isActive('link'),
    'bullet-list': () => editor.isActive('bulletList'),
    'ordered-list': () => editor.isActive('orderedList'),
    blockquote: () => editor.isActive('blockquote'),
    'code-block': () => editor.isActive('codeBlock'),
  }
  const update = () => {
    for (const button of buttons) {
      const active = activeChecks[button.dataset.command || '']?.() ?? false
      button.classList.toggle('is-active', active)
      button.setAttribute('aria-pressed', String(active))
    }
  }
  editor.on('selectionUpdate', update)
  editor.on('transaction', update)
  update()
  return () => {
    editor.off('selectionUpdate', update)
    editor.off('transaction', update)
  }
}
