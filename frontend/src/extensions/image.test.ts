import { afterEach, describe, expect, it, vi } from 'vitest'

import { createStudioEditor } from '../editor'
import { StudioImage, insertUploadedImage, uploadImageFile } from './image'

const editors: ReturnType<typeof createStudioEditor>[] = []

afterEach(() => {
  editors.splice(0).forEach((editor) => editor.destroy())
  document.body.replaceChildren()
  vi.unstubAllGlobals()
})

describe('StudioImage', () => {
  it('stores the server asset id and normalized dimensions in editor JSON', () => {
    const element = document.createElement('div')
    document.body.append(element)
    const editor = createStudioEditor({ element, extensions: [StudioImage] })
    editors.push(editor)

    insertUploadedImage(editor, {
      id: 18,
      url: '/media/assets/2026/08/safe.png',
      alt: '冷站设备',
      title: '设备照片',
      width: 1200,
      height: 800,
    })

    const imageNode = editor.getJSON().content?.find((node) => node.type === 'image')
    expect(imageNode).toMatchObject({
      type: 'image',
      attrs: {
        assetId: 18,
        src: '/media/assets/2026/08/safe.png',
        width: 1200,
        height: 800,
      },
    })
  })

  it('returns only the asset confirmed by the upload API', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        asset: {
          id: 7,
          url: '/media/assets/safe.webp',
          alt: '',
          title: 'safe',
          width: 20,
          height: 10,
        },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await uploadImageFile(
      new File(['image'], 'safe.webp', { type: 'image/webp' }),
      '/cms/api/assets/images/',
      'csrf-value',
    )

    expect(result.id).toBe(7)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(request.headers).toEqual({ 'X-CSRFToken': 'csrf-value' })
    expect(request.body).toBeInstanceOf(FormData)
  })

  it('reports the server error without creating a usable image result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ message: '图片格式不受支持' }),
    }))

    await expect(uploadImageFile(
      new File(['bad'], 'bad.svg', { type: 'image/svg+xml' }),
      '/cms/api/assets/images/',
      'csrf-value',
    )).rejects.toThrow('图片格式不受支持')
  })
})
