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
import { createPasteCleanupExtension } from './paste'
import { defaultSlashCommands, setupSlashMenu } from './slash-menu'
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
  ]
  const editor = createStudioEditor({
    element: requiredElement<HTMLElement>(root, '[data-editor-surface]'),
    content: body,
    extensions: editorExtensions,
    onChange: (document) => {
      body = document
      controller.markDirty()
    },
  })

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
    defaultSlashCommands({ onImage: () => imageInput.click() }),
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
  mountArticleEditor(root, JSON.parse(configElement.textContent) as ArticleConfig)
}
