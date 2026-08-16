import { Editor, type JSONContent } from '@tiptap/core'
import { TableKit } from '@tiptap/extension-table'
import StarterKit from '@tiptap/starter-kit'

import './editor.css'

export type StudioDocument = JSONContent

export interface StudioEditorOptions {
  element: HTMLElement
  content?: StudioDocument
  editable?: boolean
  onChange?: (document: StudioDocument) => void
}

export function createStudioEditor({
  element,
  content = { type: 'doc', content: [{ type: 'paragraph' }] },
  editable = true,
  onChange,
}: StudioEditorOptions): Editor {
  return new Editor({
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
    ],
    editorProps: {
      attributes: {
        class: 'studio-editor',
        role: 'textbox',
        'aria-multiline': 'true',
        'aria-label': '正文编辑器',
      },
    },
    onUpdate: ({ editor }) => onChange?.(editor.getJSON()),
  })
}
