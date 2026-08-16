import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AutosaveController, SaveRequestError, readStoredDraft } from './autosave'

interface Draft {
  title: string
}

const controllers: AutosaveController<Draft>[] = []

function controllerFor(save: (draft: Draft) => Promise<{ article: never }>) {
  let draft = { title: '初稿' }
  const onState = vi.fn()
  const controller = new AutosaveController({
    snapshot: () => draft,
    save,
    onState,
    storageKey: 'studio:test',
    debounceMs: 100,
    intervalMs: 30_000,
  })
  controllers.push(controller)
  return { controller, onState, setDraft: (next: Draft) => (draft = next) }
}

beforeEach(() => {
  vi.useFakeTimers()
  localStorage.clear()
})

afterEach(() => {
  controllers.splice(0).forEach((controller) => controller.destroy())
  vi.useRealTimers()
})

describe('AutosaveController', () => {
  it('debounces edits and clears the local copy after a successful save', async () => {
    const save = vi.fn().mockResolvedValue({ article: {} })
    const { controller, onState } = controllerFor(save)

    controller.markDirty()
    controller.markDirty()
    expect(readStoredDraft<Draft>('studio:test')?.draft.title).toBe('初稿')
    await vi.advanceTimersByTimeAsync(100)

    expect(save).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('studio:test')).toBeNull()
    expect(onState).toHaveBeenLastCalledWith('saved', '已保存')
  })

  it('does not discard changes made while a request is in flight', async () => {
    let resolveSave: ((value: { article: never }) => void) | undefined
    const save = vi.fn(() => new Promise<{ article: never }>((resolve) => (resolveSave = resolve)))
    const { controller, setDraft } = controllerFor(save)

    controller.markDirty()
    const pending = controller.flush()
    setDraft({ title: '请求期间的新修改' })
    controller.markDirty()
    resolveSave?.({ article: {} as never })
    await pending

    expect(controller.hasUnsavedChanges()).toBe(true)
    expect(readStoredDraft<Draft>('studio:test')?.draft.title).toBe('请求期间的新修改')
  })

  it('keeps both the normal draft and a conflict copy on version conflict', async () => {
    const save = vi.fn().mockRejectedValue(
      new SaveRequestError('文章已在别处更新', 'version_conflict', 4),
    )
    const { controller, onState } = controllerFor(save)

    controller.markDirty()
    await controller.flush()

    expect(localStorage.getItem('studio:test')).not.toBeNull()
    const conflictKeys = Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index))
      .filter((key) => key?.startsWith('studio:test:conflict:'))
    expect(conflictKeys).toHaveLength(1)
    expect(onState).toHaveBeenLastCalledWith('conflict', '文章已在别处更新')
  })

  it('moves the local draft when a new article receives its permanent id', () => {
    const { controller } = controllerFor(vi.fn().mockResolvedValue({ article: {} }))
    controller.markDirty()

    controller.setStorageKey('studio:article:42')

    expect(localStorage.getItem('studio:test')).toBeNull()
    expect(localStorage.getItem('studio:article:42')).not.toBeNull()
  })
})
