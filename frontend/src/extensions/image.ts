import type { Editor } from '@tiptap/core'
import FileHandler from '@tiptap/extension-file-handler'
import Image from '@tiptap/extension-image'

export interface UploadedImage {
  id: number
  url: string
  alt: string
  title: string
  width: number
  height: number
}

interface ImageUploadOptions {
  upload: (file: File) => Promise<UploadedImage>
  onStatus: (message: string, failed?: boolean) => void
}

const ACCEPTED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp']

export const StudioImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      assetId: { default: null },
      width: { default: null },
      height: { default: null },
    }
  },
}).configure({
  inline: false,
  allowBase64: false,
})

export function insertUploadedImage(
  editor: Editor,
  image: UploadedImage,
  position?: number,
): void {
  const node = {
    type: 'image',
    attrs: {
      assetId: image.id,
      src: image.url,
      alt: image.alt,
      title: image.title,
      width: image.width,
      height: image.height,
    },
  }
  if (position === undefined) editor.chain().focus().insertContent(node).run()
  else editor.chain().focus().insertContentAt(position, node).run()
}

export function createImageExtensions(options: ImageUploadOptions) {
  const uploadFiles = async (editor: Editor, files: File[], position?: number) => {
    let insertionPosition = position
    for (const file of files.filter((item) => ACCEPTED_MIME_TYPES.includes(item.type))) {
      options.onStatus(`正在上传 ${file.name}…`)
      try {
        const image = await options.upload(file)
        insertUploadedImage(editor, image, insertionPosition)
        if (insertionPosition !== undefined) insertionPosition += 1
        options.onStatus('图片已上传并插入')
      } catch (error) {
        options.onStatus(error instanceof Error ? error.message : '图片上传失败', true)
      }
    }
  }
  return [
    StudioImage,
    FileHandler.configure({
      allowedMimeTypes: ACCEPTED_MIME_TYPES,
      onDrop: (editor, files, position) => void uploadFiles(editor, files, position),
      onPaste: (editor, files) => void uploadFiles(editor, files),
    }),
  ]
}

export async function uploadImageFile(
  file: File,
  uploadUrl: string,
  csrfToken: string,
): Promise<UploadedImage> {
  const form = new FormData()
  form.append('image', file)
  const response = await fetch(uploadUrl, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': csrfToken },
    body: form,
  })
  const payload = await response.json() as {
    asset?: UploadedImage
    message?: string
  }
  if (!response.ok || !payload.asset) throw new Error(payload.message || '图片上传失败。')
  return payload.asset
}
