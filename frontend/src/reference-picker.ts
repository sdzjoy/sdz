export type ReferenceKind = 'standard' | 'resource'

interface ReferenceOption {
  id: number
  label: string
  description: string
}

interface ReferencePickerOptions {
  kind: ReferenceKind
  searchUrl: string
  title: string
  placeholder: string
}

export function chooseReference(options: ReferencePickerOptions): Promise<number | null> {
  return new Promise((resolve) => {
    const overlay = document.createElement('div')
    overlay.className = 'studio-picker-overlay'
    overlay.setAttribute('role', 'dialog')
    overlay.setAttribute('aria-modal', 'true')
    overlay.setAttribute('aria-label', options.title)
    const panel = document.createElement('div')
    panel.className = 'studio-picker-panel'
    const header = document.createElement('header')
    const heading = document.createElement('strong')
    heading.textContent = options.title
    const cancel = document.createElement('button')
    cancel.type = 'button'
    cancel.textContent = '取消'
    const input = document.createElement('input')
    input.type = 'search'
    input.placeholder = options.placeholder
    input.setAttribute('aria-label', options.placeholder)
    const results = document.createElement('div')
    results.className = 'studio-picker-results'
    results.setAttribute('aria-live', 'polite')
    header.append(heading, cancel)
    panel.append(header, input, results)
    overlay.append(panel)
    document.body.append(overlay)
    let timer: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | undefined
    let finished = false

    const finish = (value: number | null) => {
      if (finished) return
      finished = true
      if (timer) clearTimeout(timer)
      controller?.abort()
      overlay.remove()
      resolve(value)
    }
    const render = (items: ReferenceOption[]) => {
      if (!items.length) {
        results.textContent = '没有找到匹配记录。'
        return
      }
      results.replaceChildren(...items.map((item) => {
        const button = document.createElement('button')
        button.type = 'button'
        const label = document.createElement('strong')
        label.textContent = item.label
        const description = document.createElement('small')
        description.textContent = item.description
        button.append(label, description)
        button.addEventListener('click', () => finish(item.id))
        return button
      }))
    }
    const search = async () => {
      controller?.abort()
      controller = new AbortController()
      results.textContent = '正在查找…'
      const url = new URL(options.searchUrl, window.location.origin)
      url.searchParams.set('kind', options.kind)
      url.searchParams.set('q', input.value.trim())
      try {
        const response = await fetch(url, {
          credentials: 'same-origin',
          signal: controller.signal,
        })
        const payload = await response.json() as { items?: ReferenceOption[]; message?: string }
        if (!response.ok || !payload.items) throw new Error(payload.message || '查找失败')
        render(payload.items)
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          results.textContent = error instanceof Error ? error.message : '查找失败'
        }
      }
    }
    const scheduleSearch = () => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => void search(), 220)
    }
    cancel.addEventListener('click', () => finish(null))
    overlay.addEventListener('pointerdown', (event) => {
      if (event.target === overlay) finish(null)
    })
    overlay.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') finish(null)
    })
    input.addEventListener('input', scheduleSearch)
    input.focus()
    void search()
  })
}
