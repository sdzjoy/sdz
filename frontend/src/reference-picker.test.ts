import { afterEach, describe, expect, it, vi } from 'vitest'

import { chooseReference } from './reference-picker'

afterEach(() => {
  document.body.replaceChildren()
  vi.unstubAllGlobals()
})

describe('reference picker', () => {
  it('searches by readable text and resolves the selected record id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        items: [{
          id: 74,
          label: 'GB 50174-2017',
          description: '数据中心设计规范 · 现行',
        }],
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const selection = chooseReference({
      kind: 'standard',
      searchUrl: '/cms/api/references/',
      title: '选择规范',
      placeholder: '输入标准编号或名称',
    })
    await vi.waitFor(() => {
      expect(document.querySelector('.studio-picker-results button')).not.toBeNull()
    })
    document.querySelector<HTMLButtonElement>('.studio-picker-results button')?.click()

    await expect(selection).resolves.toBe(74)
    const requestUrl = String(fetchMock.mock.calls[0]?.[0])
    expect(requestUrl).toContain('kind=standard')
  })

  it('returns null when the picker is cancelled', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise(() => {})))
    const selection = chooseReference({
      kind: 'resource',
      searchUrl: '/cms/api/references/',
      title: '选择资源',
      placeholder: '输入资源名称',
    })

    document.querySelector<HTMLButtonElement>('.studio-picker-panel header button')?.click()

    await expect(selection).resolves.toBeNull()
    expect(document.querySelector('.studio-picker-overlay')).toBeNull()
  })
})
