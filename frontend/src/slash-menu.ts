import type { Editor } from '@tiptap/core'

export interface SlashCommand {
  id: string
  label: string
  description: string
  keywords: string
  run: (editor: Editor) => void
}

interface SlashMenuOptions {
  onImage: () => void
  extraCommands?: SlashCommand[]
}

export function defaultSlashCommands(options: SlashMenuOptions): SlashCommand[] {
  return [
    { id: 'paragraph', label: '正文', description: '普通正文段落', keywords: 'paragraph text 正文', run: (editor) => { editor.chain().focus().setParagraph().run() } },
    { id: 'heading2', label: '二级标题', description: '文章主要章节', keywords: 'h2 heading 标题', run: (editor) => { editor.chain().focus().toggleHeading({ level: 2 }).run() } },
    { id: 'heading3', label: '三级标题', description: '章节内的小标题', keywords: 'h3 heading 标题', run: (editor) => { editor.chain().focus().toggleHeading({ level: 3 }).run() } },
    { id: 'bullet', label: '项目符号', description: '无序列表', keywords: 'bullet list 列表', run: (editor) => { editor.chain().focus().toggleBulletList().run() } },
    { id: 'ordered', label: '编号列表', description: '有顺序的列表', keywords: 'ordered number list 编号', run: (editor) => { editor.chain().focus().toggleOrderedList().run() } },
    { id: 'quote', label: '引用', description: '引用一段原文', keywords: 'quote blockquote 引用', run: (editor) => { editor.chain().focus().toggleBlockquote().run() } },
    { id: 'code', label: '代码块', description: '等宽代码段', keywords: 'code 代码', run: (editor) => { editor.chain().focus().toggleCodeBlock().run() } },
    { id: 'divider', label: '分隔线', description: '分开两部分内容', keywords: 'divider hr 分隔线', run: (editor) => { editor.chain().focus().setHorizontalRule().run() } },
    { id: 'table', label: '表格', description: '插入 3 × 3 表格', keywords: 'table 表格', run: (editor) => { editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run() } },
    { id: 'image', label: '图片', description: '从本机安全上传', keywords: 'image photo 图片 照片', run: () => options.onImage() },
    ...(options.extraCommands || []),
  ]
}

export function setupSlashMenu(
  host: HTMLElement,
  editor: Editor,
  commands: SlashCommand[],
) {
  const menu = document.createElement('div')
  menu.className = 'studio-slash-menu'
  menu.hidden = true
  menu.setAttribute('role', 'dialog')
  menu.setAttribute('aria-label', '插入内容')
  const input = document.createElement('input')
  input.type = 'search'
  input.placeholder = '搜索要插入的内容'
  input.setAttribute('aria-label', '搜索插入项')
  const list = document.createElement('div')
  list.className = 'studio-slash-results'
  list.setAttribute('role', 'listbox')
  menu.append(input, list)
  host.append(menu)
  let filtered = commands
  let activeIndex = 0

  const execute = (command: SlashCommand) => {
    menu.hidden = true
    input.value = ''
    command.run(editor)
  }
  const render = () => {
    const query = input.value.trim().toLocaleLowerCase('zh-CN')
    filtered = commands.filter((command) => (
      `${command.label} ${command.description} ${command.keywords}`
        .toLocaleLowerCase('zh-CN')
        .includes(query)
    ))
    activeIndex = Math.min(activeIndex, Math.max(filtered.length - 1, 0))
    list.replaceChildren(...filtered.map((command, index) => {
      const button = document.createElement('button')
      button.type = 'button'
      button.setAttribute('role', 'option')
      button.setAttribute('aria-selected', String(index === activeIndex))
      button.className = index === activeIndex ? 'is-active' : ''
      const label = document.createElement('strong')
      label.textContent = command.label
      const description = document.createElement('small')
      description.textContent = command.description
      button.append(label, description)
      button.addEventListener('click', () => execute(command))
      return button
    }))
  }
  const open = () => {
    const coordinates = editor.view.coordsAtPos(editor.state.selection.from)
    menu.style.left = `${Math.min(coordinates.left, window.innerWidth - 330)}px`
    menu.style.top = `${Math.min(coordinates.bottom + 8, window.innerHeight - 420)}px`
    menu.hidden = false
    activeIndex = 0
    render()
    input.focus()
  }
  const close = () => {
    menu.hidden = true
    input.value = ''
    editor.commands.focus()
  }
  const editorKeydown = (event: Event) => {
    const keyboardEvent = event as KeyboardEvent
    if (
      keyboardEvent.isComposing
      || keyboardEvent.ctrlKey
      || keyboardEvent.metaKey
      || keyboardEvent.altKey
      || keyboardEvent.key !== '/'
    ) return
    keyboardEvent.preventDefault()
    open()
  }
  const inputKeydown = (event: KeyboardEvent) => {
    if (event.isComposing) return
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
    } else if (event.key === 'ArrowDown' && filtered.length) {
      event.preventDefault()
      activeIndex = (activeIndex + 1) % filtered.length
      render()
    } else if (event.key === 'ArrowUp' && filtered.length) {
      event.preventDefault()
      activeIndex = (activeIndex - 1 + filtered.length) % filtered.length
      render()
    } else if (event.key === 'Enter' && filtered[activeIndex]) {
      event.preventDefault()
      const command = filtered[activeIndex]
      if (command) execute(command)
    }
  }
  editor.view.dom.addEventListener('keydown', editorKeydown)
  input.addEventListener('input', render)
  input.addEventListener('keydown', inputKeydown)
  document.addEventListener('pointerdown', (event) => {
    if (!menu.hidden && !menu.contains(event.target as Node)) menu.hidden = true
  })
  return { open, close }
}
