import { describe, expect, it, vi } from 'vitest'

import { cleanPastedHTML, createPasteCleanupExtension, sanitizePastedHTML } from './paste'

describe('paste cleanup', () => {
  it('preserves semantic structure while removing source styles and executable markup', () => {
    const result = sanitizePastedHTML(`
      <h1 style="font-size: 80px" onclick="alert(1)">冷源设计<script>alert(2)</script></h1>
      <p class="MsoNormal"><b>重点</b><span style="color:red">参数</span></p>
      <blockquote data-source="wechat">引用内容</blockquote>
      <table style="width:999px"><tr><td colspan="2" onmouseover="bad()">表格</td></tr></table>
      <a href="javascript:alert(3)" target="_blank">危险链接</a>
    `)

    expect(result.html).toContain('<h2>冷源设计</h2>')
    expect(result.html).toContain('<strong>重点</strong>参数')
    expect(result.html).toContain('<blockquote>引用内容</blockquote>')
    expect(result.html).toContain('<td colspan="2">表格</td>')
    expect(result.html).not.toMatch(/style=|class=|onclick|onmouseover|script|javascript:/)
  })

  it('removes pasted external images and reports that they need uploading', () => {
    const result = sanitizePastedHTML(
      '<p>图片前</p><img src="https://example.com/temporary.jpg"><p>图片后</p>',
    )

    expect(result.externalImages).toBe(1)
    expect(result.html).not.toContain('<img')
    expect(result.html).not.toContain('example.com')
  })

  it('falls back to escaped plain text if structured cleanup fails', () => {
    const result = cleanPastedHTML(
      '<p>保留 &amp; 文本</p>',
      () => { throw new Error('simulated sanitizer failure') },
    )

    expect(result.fellBackToText).toBe(true)
    expect(result.html).toBe('<p>保留 &amp; 文本</p>')
  })

  it('notifies the editor when external images are discarded', () => {
    const warning = vi.fn()
    const extension = createPasteCleanupExtension(warning)
    const transform = extension.config.transformPastedHTML

    const cleaned = transform?.call(
      { editor: undefined } as never,
      '<p>正文</p><img src="https://example.com/a.jpg">',
    )

    expect(cleaned).not.toContain('<img')
    expect(warning).toHaveBeenCalledWith('外部图片地址没有粘贴，请使用“图片”重新上传。')
  })
})
