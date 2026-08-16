export type SaveIntent = 'autosave' | 'save' | 'publish'
export type SaveState = 'dirty' | 'saving' | 'saved' | 'offline' | 'failed' | 'conflict'

export interface SavedArticle {
  id: number
  version: number
  status: string
  edit_url: string
  preview_url: string
  public_url: string
  autosave_url: string
  save_url: string
  publish_url: string
}

export interface SaveResult {
  article: SavedArticle
}

export interface StoredDraft<TDraft> {
  savedAt: string
  draft: TDraft
}

export class SaveRequestError extends Error {
  constructor(
    message: string,
    readonly code = 'save_failed',
    readonly currentVersion?: number,
  ) {
    super(message)
    this.name = 'SaveRequestError'
  }
}

interface AutosaveOptions<TDraft> {
  snapshot: () => TDraft
  save: (draft: TDraft, intent: SaveIntent) => Promise<SaveResult>
  onState: (state: SaveState, message: string) => void
  onSaved?: (result: SaveResult) => void
  storageKey: string
  debounceMs?: number
  intervalMs?: number
}

const STATE_MESSAGES: Record<SaveState, string> = {
  dirty: '有未保存的修改',
  saving: '正在保存…',
  saved: '已保存',
  offline: '网络不可用，草稿已保存在本机',
  failed: '保存失败，草稿已保存在本机',
  conflict: '检测到其他窗口的修改，已保留当前副本',
}

export function readStoredDraft<TDraft>(storageKey: string): StoredDraft<TDraft> | null {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredDraft<TDraft>
    if (!parsed || typeof parsed !== 'object' || !parsed.draft) return null
    return parsed
  } catch {
    return null
  }
}

export class AutosaveController<TDraft> {
  private storageKey: string
  private debounceTimer: ReturnType<typeof setTimeout> | undefined
  private intervalTimer: ReturnType<typeof setInterval>
  private dirty = false
  private saving = false
  private changeNumber = 0
  private destroyed = false

  constructor(private readonly options: AutosaveOptions<TDraft>) {
    this.storageKey = options.storageKey
    this.intervalTimer = setInterval(
      () => void this.flush('autosave'),
      options.intervalMs ?? 30_000,
    )
  }

  markDirty(): void {
    if (this.destroyed) return
    this.dirty = true
    this.changeNumber += 1
    this.storeLocalDraft()
    this.setState('dirty')
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
    this.debounceTimer = setTimeout(
      () => void this.flush('autosave'),
      this.options.debounceMs ?? 1_200,
    )
  }

  async flush(intent: SaveIntent = 'autosave'): Promise<SaveResult | null> {
    if (this.destroyed || this.saving || (intent === 'autosave' && !this.dirty)) return null
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
    const savedChangeNumber = this.changeNumber
    const draft = this.options.snapshot()
    this.saving = true
    this.setState('saving')
    try {
      const result = await this.options.save(draft, intent)
      this.options.onSaved?.(result)
      if (savedChangeNumber === this.changeNumber) {
        this.dirty = false
        this.removeLocalDraft()
        this.setState('saved')
      } else {
        this.setState('dirty')
        this.scheduleNextSave()
      }
      return result
    } catch (error) {
      this.storeLocalDraft()
      if (error instanceof SaveRequestError && error.code === 'version_conflict') {
        this.storeConflictCopy(draft)
        this.setState('conflict', error.message)
      } else if (!navigator.onLine) {
        this.setState('offline')
      } else {
        this.setState('failed', error instanceof Error ? error.message : undefined)
      }
      return null
    } finally {
      this.saving = false
    }
  }

  setStorageKey(storageKey: string): void {
    if (storageKey === this.storageKey) return
    const oldKey = this.storageKey
    this.storageKey = storageKey
    try {
      const existing = localStorage.getItem(oldKey)
      if (existing) localStorage.setItem(storageKey, existing)
      localStorage.removeItem(oldKey)
    } catch {
      // A browser can disable storage. Network saving must keep working.
    }
  }

  hasUnsavedChanges(): boolean {
    return this.dirty || this.saving
  }

  retryWhenOnline(): void {
    if (this.dirty) void this.flush('autosave')
  }

  destroy(): void {
    this.destroyed = true
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
    clearInterval(this.intervalTimer)
  }

  private scheduleNextSave(): void {
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
    this.debounceTimer = setTimeout(
      () => void this.flush('autosave'),
      this.options.debounceMs ?? 1_200,
    )
  }

  private setState(state: SaveState, detail?: string): void {
    this.options.onState(state, detail || STATE_MESSAGES[state])
  }

  private storeLocalDraft(): void {
    try {
      localStorage.setItem(
        this.storageKey,
        JSON.stringify({ savedAt: new Date().toISOString(), draft: this.options.snapshot() }),
      )
    } catch {
      // Storage failure must not interrupt editing.
    }
  }

  private removeLocalDraft(): void {
    try {
      localStorage.removeItem(this.storageKey)
    } catch {
      // Storage failure must not interrupt editing.
    }
  }

  private storeConflictCopy(draft: TDraft): void {
    try {
      localStorage.setItem(
        `${this.storageKey}:conflict:${Date.now()}`,
        JSON.stringify({ savedAt: new Date().toISOString(), draft }),
      )
    } catch {
      // The normal local draft remains if the extra conflict copy cannot be written.
    }
  }
}
