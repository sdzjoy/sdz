import type { JSONContent } from '@tiptap/core'

import {
  AutosaveController,
  SaveRequestError,
  readStoredDraft,
  type SaveIntent,
  type SaveResult,
} from './autosave'
import { createStudioEditor } from './editor'
import {
  createImageExtensions,
  insertUploadedImage,
  uploadImageFile,
} from './extensions/image'
import { Callout } from './extensions/callout'
import { CloudResource } from './extensions/cloud-resource'
import { Equation } from './extensions/equation'
import { ParameterCard } from './extensions/parameter-card'
import { StandardReference } from './extensions/reference'
import { createPasteCleanupExtension } from './paste'
import { chooseReference } from './reference-picker'
import {
  defaultSlashCommands,
  setupSlashMenu,
  type SlashCommand,
} from './slash-menu'
import { createToolbarExtensions, setupToolbar } from './toolbar'

interface ArticleConfig {
  schemaVersion: number
  articleId: number | null
  version: number
  status: string
  title: string
  slug: string
  summary: string
  featured: boolean
  publishedOn: string
  readingMinutes: number | null
  parentProjectId: number | null
  topicIds: number[]
  body: JSONContent
  createUrl: string
  autosaveUrl: string
  saveUrl: string
  publishUrl: string
  previewUrl: string
  imageUploadUrl: string
  referenceSearchUrl: string
}

interface ArticleDraft {
  title: string
  slug: string
  summary: string
  body_json: {
    schema_version: number
    doc: JSONContent
  }
  version: number
  featured: boolean
  published_on: string
  reading_minutes: number | null
  parent_project: number | null
  topics: number[]
}

interface ErrorResponse {
  code?: string
  message?: string
  current_version?: number
  fields?: Record<string, string[]>
}

function requiredElement<T extends Element>(root: ParentNode, selector: string): T {
  const element = root.querySelector<T>(selector)
  if (!element) throw new Error(`Missing editor element: ${selector}`)
  return element
}

function csrfToken(): string {
  return requiredElement<HTMLInputElement>(document, '[name=csrfmiddlewaretoken]').value
}

function restoreDraft(config: ArticleConfig, storageKey: string): ArticleDraft | null {
  const stored = readStoredDraft<ArticleDraft>(storageKey)
  if (!stored || stored.draft.version !== config.version) return null
  const when = new Date(stored.savedAt).toLocaleString('zh-CN')
  return window.confirm(`发现 ${when} 保存在本机但尚未上传的草稿，是否恢复？`) ? stored.draft : null
}

function professionalSlashCommands(referenceSearchUrl: string): SlashCommand[] {
  return [
    {
      id: 'callout',
      label: '提示框',
      description: '设计提示、注意事项或警告',
      keywords: 'callout tip warning 提示 注意 警告',
      run: (editor) => {
        const title = window.prompt('提示框标题', '设计提示')
        if (title === null) return
        editor.chain().focus().insertContent({
          type: 'callout',
          attrs: { variant: 'info', title: title.trim() || '设计提示' },
          content: [{ type: 'paragraph' }],
        }).run()
      },
    },
    {
      id: 'equation',
      label: '公式',
      description: '输入 LaTeX，服务器安全渲染',
      keywords: 'equation math latex 公式',
      run: (editor) => {
        const latex = window.prompt('输入 LaTeX 公式，例如 Q = mc\\Delta t')
        if (!latex?.trim()) return
        editor.chain().focus().insertContent({
          type: 'equation',
          attrs: { latex: latex.trim() },
        }).run()
      },
    },
    {
      id: 'standard-reference',
      label: '规范引用',
      description: '引用规范库中的当前记录',
      keywords: 'standard code 规范 标准 引用',
      run: (editor) => {
        void chooseReference({
          kind: 'standard',
          searchUrl: referenceSearchUrl,
          title: '选择规范',
          placeholder: '输入标准编号或名称',
        }).then((standardId) => {
          if (standardId) editor.chain().focus().insertContent({
            type: 'standardReference', attrs: { standardId },
          }).run()
        })
      },
    },
    {
      id: 'parameter-card',
      label: '参数卡',
      description: '突出展示暖通设计参数',
      keywords: 'parameter value unit 参数 数值 单位',
      run: (editor) => {
        const name = window.prompt('参数名称，例如 冷冻水供回水温差')
        if (!name?.trim()) return
        const value = window.prompt('参数值，例如 6')
        if (!value?.trim()) return
        const unit = window.prompt('单位，例如 ℃', '')
        if (unit === null) return
        const note = window.prompt('补充说明（可留空）', '')
        if (note === null) return
        editor.chain().focus().insertContent({
          type: 'parameterCard',
          attrs: {
            name: name.trim(),
            value: value.trim(),
            unit: unit.trim(),
            note: note.trim(),
          },
        }).run()
      },
    },
    {
      id: 'cloud-resource',
      label: '网盘资源',
      description: '按会员等级显示受控下载入口',
      keywords: 'cloud resource 百度网盘 阿里云盘 资源',
      run: (editor) => {
        void chooseReference({
          kind: 'resource',
          searchUrl: referenceSearchUrl,
          title: '选择网盘资源',
          placeholder: '输入资源名称',
        }).then((resourceId) => {
          if (resourceId) editor.chain().focus().insertContent({
            type: 'cloudResource', attrs: { resourceId },
          }).run()
        })
      },
    },
  ]
}

function mountArticleEditor(root: HTMLElement, initialConfig: ArticleConfig): void {
  const config = { ...initialConfig }
  let body = config.body
  let restored: ArticleDraft | null = null
  const initialStorageKey = `studio:article:${config.articleId ?? 'new'}`
  restored = restoreDraft(config, initialStorageKey)
  if (restored) body = restored.body_json.doc

  const title = requiredElement<HTMLInputElement>(root, '[data-article-title]')
  const slug = requiredElement<HTMLInputElement>(root, '[data-article-slug]')
  const summary = requiredElement<HTMLTextAreaElement>(root, '[data-article-summary]')
  const publishedOn = requiredElement<HTMLInputElement>(root, '[data-published-on]')
  const readingMinutes = requiredElement<HTMLInputElement>(root, '[data-reading-minutes]')
  const parentProject = requiredElement<HTMLSelectElement>(root, '[data-parent-project]')
  const featured = requiredElement<HTMLInputElement>(root, '[data-featured]')
  const saveState = requiredElement<HTMLElement>(root, '[data-save-state]')
  const previewButton = requiredElement<HTMLButtonElement>(root, '[data-preview]')
  const saveButton = requiredElement<HTMLButtonElement>(root, '[data-save]')
  const publishButton = requiredElement<HTMLButtonElement>(root, '[data-publish]')
  const imageButton = requiredElement<HTMLButtonElement>(root, '[data-upload-image]')
  const imageInput = requiredElement<HTMLInputElement>(root, '[data-image-input]')
  const floatingToolbar = requiredElement<HTMLElement>(root, '[data-floating-toolbar]')
  const editorSurface = requiredElement<HTMLElement>(root, '[data-editor-surface]')

  if (restored) {
    title.value = restored.title
    slug.value = restored.slug
    summary.value = restored.summary
    publishedOn.value = restored.published_on
    readingMinutes.value = restored.reading_minutes?.toString() ?? ''
    parentProject.value = restored.parent_project?.toString() ?? ''
    featured.checked = restored.featured
    const selected = new Set(restored.topics)
    root.querySelectorAll<HTMLInputElement>('[data-topic]').forEach((input) => {
      input.checked = selected.has(Number(input.value))
    })
  }

  let controller: AutosaveController<ArticleDraft>
  const imageExtensions = createImageExtensions({
    upload: (file) => uploadImageFile(file, config.imageUploadUrl, csrfToken()),
    onStatus: (message, failed = false) => {
      saveState.dataset.state = failed ? 'failed' : 'saving'
      saveState.textContent = message
    },
  })
  const editorExtensions = [
    ...imageExtensions,
    ...createToolbarExtensions(floatingToolbar),
    createPasteCleanupExtension((message) => {
      saveState.dataset.state = 'dirty'
      saveState.textContent = message
    }),
    Callout,
    Equation,
    StandardReference,
    ParameterCard,
    CloudResource,
  ]
  editorSurface.replaceChildren()
  const editor = createStudioEditor({
    element: editorSurface,
    content: body,
    extensions: editorExtensions,
    onChange: (document) => {
      body = document
      controller.markDirty()
    },
  })
  editorSurface.dataset.ready = 'true'

  const snapshot = (): ArticleDraft => ({
    title: title.value.trim(),
    slug: slug.value.trim(),
    summary: summary.value.trim(),
    body_json: { schema_version: config.schemaVersion, doc: body },
    version: config.version,
    featured: featured.checked,
    published_on: publishedOn.value,
    reading_minutes: readingMinutes.value ? Number(readingMinutes.value) : null,
    parent_project: parentProject.value ? Number(parentProject.value) : null,
    topics: Array.from(root.querySelectorAll<HTMLInputElement>('[data-topic]:checked')).map((input) => Number(input.value)),
  })

  const endpointFor = (intent: SaveIntent): string => {
    if (!config.articleId) return config.createUrl
    if (intent === 'publish') return config.publishUrl
    if (intent === 'save') return config.saveUrl
    return config.autosaveUrl
  }

  const save = async (draft: ArticleDraft, intent: SaveIntent): Promise<SaveResult> => {
    const response = await fetch(endpointFor(intent), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify({ ...draft, intent }),
    })
    const payload = (await response.json()) as SaveResult & ErrorResponse
    if (!response.ok) {
      const fieldMessage = payload.fields ? Object.values(payload.fields).flat()[0] : undefined
      throw new SaveRequestError(
        fieldMessage || payload.message || '保存失败，请稍后重试。',
        payload.code,
        payload.current_version,
      )
    }
    return payload
  }

  controller = new AutosaveController({
    snapshot,
    save,
    storageKey: initialStorageKey,
    onState: (state, message) => {
      saveState.dataset.state = state
      saveState.textContent = message
    },
    onSaved: ({ article }) => {
      const wasNew = config.articleId === null
      config.articleId = article.id
      config.version = article.version
      config.status = article.status
      config.autosaveUrl = article.autosave_url
      config.saveUrl = article.save_url
      config.publishUrl = article.publish_url
      config.previewUrl = article.preview_url
      controller.setStorageKey(`studio:article:${article.id}`)
      if (wasNew) window.history.replaceState({}, '', article.edit_url)
      if (article.status === 'published') {
        saveState.textContent = '已发布'
      }
    },
  })

  if (restored) controller.markDirty()
  root.querySelectorAll<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>('input, textarea, select').forEach((input) => {
    input.addEventListener('input', () => controller.markDirty())
    input.addEventListener('change', () => controller.markDirty())
  })
  setupToolbar(root, editor)
  const slashMenu = setupSlashMenu(
    root,
    editor,
    defaultSlashCommands({
      onImage: () => imageInput.click(),
      extraCommands: professionalSlashCommands(config.referenceSearchUrl),
    }),
  )
  requiredElement<HTMLButtonElement>(root, '[data-open-slash]')
    .addEventListener('click', slashMenu.open)
  imageButton.addEventListener('click', () => imageInput.click())
  imageInput.addEventListener('change', () => {
    const file = imageInput.files?.[0]
    if (!file) return
    saveState.dataset.state = 'saving'
    saveState.textContent = `正在上传 ${file.name}…`
    void uploadImageFile(file, config.imageUploadUrl, csrfToken())
      .then((image) => insertUploadedImage(editor, image))
      .catch((error: unknown) => {
        saveState.dataset.state = 'failed'
        saveState.textContent = error instanceof Error ? error.message : '图片上传失败'
      })
      .finally(() => { imageInput.value = '' })
  })

  saveButton.addEventListener('click', () => void controller.flush('save'))
  publishButton.addEventListener('click', () => void controller.flush('publish'))
  previewButton.addEventListener('click', async () => {
    const result = controller.hasUnsavedChanges() || !config.articleId
      ? await controller.flush('save')
      : null
    const previewUrl = result?.article.preview_url || config.previewUrl
    if (previewUrl) window.open(previewUrl, '_blank', 'noopener')
  })
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault()
      void controller.flush('save')
    }
  })
  window.addEventListener('online', () => controller.retryWhenOnline())
  window.addEventListener('beforeunload', (event) => {
    if (!controller.hasUnsavedChanges()) return
    event.preventDefault()
  })
}

const root = document.querySelector<HTMLElement>('[data-article-editor]')
const configElement = document.querySelector<HTMLScriptElement>('#article-editor-config')
if (root && configElement?.textContent) {
  try {
    mountArticleEditor(root, JSON.parse(configElement.textContent) as ArticleConfig)
  } catch (error) {
    const surface = root.querySelector<HTMLElement>('[data-editor-surface]')
    if (surface) {
      surface.replaceChildren()
      const message = document.createElement('p')
      message.className = 'article-editor-error'
      message.textContent = '正文编辑器加载失败，请刷新页面；如果仍然失败，请返回内容列表后重试。'
      surface.append(message)
    }
    console.error('Article editor failed to initialize', error)
  }
}
