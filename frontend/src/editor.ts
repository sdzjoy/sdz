import { Editor, type AnyExtension, type JSONContent } from '@tiptap/core'
import { TableKit } from '@tiptap/extension-table'
import StarterKit from '@tiptap/starter-kit'

import './editor.css'

export type StudioDocument = JSONContent

export interface StudioEditorOptions {
  element: HTMLElement
  content?: StudioDocument
  editable?: boolean
  placeholder?: string
  onChange?: (document: StudioDocument) => void
  extensions?: AnyExtension[]
}

function syncEmptyState(editor: Editor): void {
  editor.view.dom.dataset.empty = String(editor.isEmpty)
}

export function createStudioEditor({
  element,
  content = { type: 'doc', content: [{ type: 'paragraph' }] },
  editable = true,
  placeholder = '从这里开始写正文，输入 / 可以插入图片、参数卡和规范引用',
  onChange,
  extensions = [],
}: StudioEditorOptions): Editor {
  const editor = new Editor({
    element,
    content,
    editable,
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [2, 3],
        },
        link: {
          openOnClick: false,
          autolink: true,
          defaultProtocol: 'https',
        },
      }),
      TableKit.configure({
        table: {
          resizable: true,
        },
      }),
      ...extensions,
    ],
    editorProps: {
      attributes: {
        class: 'studio-editor',
        role: 'textbox',
        'aria-multiline': 'true',
        'aria-label': '正文编辑器',
        'data-placeholder': placeholder,
      },
    },
    onCreate: ({ editor }) => syncEmptyState(editor),
    onUpdate: ({ editor }) => {
      syncEmptyState(editor)
      onChange?.(editor.getJSON())
    },
  })
  syncEmptyState(editor)
  return editor
}
