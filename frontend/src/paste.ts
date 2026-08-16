import { Extension } from '@tiptap/core'

const ALLOWED_TAGS = new Set([
  'a', 'blockquote', 'br', 'code', 'em', 'h2', 'h3', 'hr', 'li', 'ol', 'p',
  'pre', 's', 'strong', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'u', 'ul',
])
const DROP_WITH_CONTENT = new Set(['script', 'style', 'iframe', 'object', 'embed', 'svg', 'math'])

export interface PasteCleanupResult {
  html: string
  externalImages: number
  fellBackToText: boolean
}

function safeHref(value: string): boolean {
  if ((value.startsWith('/') && !value.startsWith('//')) || value.startsWith('#')) return true
  try {
    return ['http:', 'https:', 'mailto:'].includes(new URL(value).protocol)
  } catch {
    return false
  }
}

function replaceTag(element: Element, tagName: string): Element {
  const replacement = document.createElement(tagName)
  replacement.append(...Array.from(element.childNodes))
  element.replaceWith(replacement)
  return replacement
}

export function sanitizePastedHTML(source: string): PasteCleanupResult {
  const parsed = new DOMParser().parseFromString(source, 'text/html')
  let externalImages = 0
  const elements = Array.from(parsed.body.querySelectorAll('*')).reverse()
  for (let current of elements) {
    let tag = current.tagName.toLowerCase()
    if (tag === 'img') {
      externalImages += 1
      current.remove()
      continue
    }
    if (DROP_WITH_CONTENT.has(tag)) {
      current.remove()
      continue
    }
    if (tag === 'h1') current = replaceTag(current, 'h2')
    else if (/^h[4-6]$/.test(tag)) current = replaceTag(current, 'h3')
    else if (tag === 'b') current = replaceTag(current, 'strong')
    else if (tag === 'i') current = replaceTag(current, 'em')
    else if (tag === 'del') current = replaceTag(current, 's')
    tag = current.tagName.toLowerCase()
    if (!ALLOWED_TAGS.has(tag)) {
      current.replaceWith(...Array.from(current.childNodes))
      continue
    }

    const originalAttributes = Object.fromEntries(
      Array.from(current.attributes).map((attribute) => [attribute.name, attribute.value]),
    )
    for (const attribute of Array.from(current.attributes)) current.removeAttribute(attribute.name)
    if (tag === 'a') {
      const href = originalAttributes.href || ''
      if (safeHref(href)) {
        current.setAttribute('href', href)
        if (originalAttributes.title) current.setAttribute('title', originalAttributes.title.slice(0, 300))
      }
    } else if (tag === 'ol') {
      const start = Number(originalAttributes.start)
      if (Number.isInteger(start) && start > 1 && start <= 1_000_000) current.setAttribute('start', String(start))
    } else if (tag === 'td' || tag === 'th') {
      for (const name of ['colspan', 'rowspan']) {
        const value = Number(originalAttributes[name])
        if (Number.isInteger(value) && value > 1 && value <= 20) current.setAttribute(name, String(value))
      }
    }
  }
  return { html: parsed.body.innerHTML, externalImages, fellBackToText: false }
}

function escapeHTML(value: string): string {
  const element = document.createElement('div')
  element.textContent = value
  return element.innerHTML
}

export function cleanPastedHTML(
  source: string,
  sanitizer: (value: string) => PasteCleanupResult = sanitizePastedHTML,
): PasteCleanupResult {
  try {
    return sanitizer(source)
  } catch {
    let text = ''
    try {
      text = new DOMParser().parseFromString(source, 'text/html').body.textContent || ''
    } catch {
      text = source.replace(/<[^>]*>/g, ' ')
    }
    const paragraphs = text.split(/\r?\n/).map((line) => `<p>${escapeHTML(line)}</p>`).join('')
    return { html: paragraphs || '<p></p>', externalImages: 0, fellBackToText: true }
  }
}

export function createPasteCleanupExtension(onWarning: (message: string) => void) {
  return Extension.create({
    name: 'studioPasteCleanup',
    priority: 1000,
    transformPastedHTML(html) {
      const result = cleanPastedHTML(html)
      if (result.externalImages) onWarning('外部图片地址没有粘贴，请使用“图片”重新上传。')
      if (result.fellBackToText) onWarning('来源排版无法安全清理，已按纯文本粘贴。')
      return result.html
    },
  })
}
