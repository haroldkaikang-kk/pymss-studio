import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { createEditorAudioElement, waitForEditorAudioReady } from '../src/utils/editorAudio.ts'

describe('editor audio element setup', () => {
  it('sets CORS before assigning the asset URL', () => {
    const originalAudio = globalThis.Audio
    const operations: string[] = []

    class FakeAudio {
      private _crossOrigin = ''
      private _preload = ''
      private _loop = false
      private _src = ''

      get crossOrigin() { return this._crossOrigin }
      set crossOrigin(value: string) {
        operations.push('crossOrigin')
        this._crossOrigin = value
      }

      get preload() { return this._preload }
      set preload(value: string) {
        operations.push('preload')
        this._preload = value
      }

      get loop() { return this._loop }
      set loop(value: boolean) {
        operations.push('loop')
        this._loop = value
      }

      get src() { return this._src }
      set src(value: string) {
        operations.push('src')
        this._src = value
      }
    }

    Object.defineProperty(globalThis, 'Audio', {
      configurable: true,
      value: FakeAudio,
    })

    try {
      const audio = createEditorAudioElement('asset://localhost/audio.wav')
      assert.deepEqual(operations, ['crossOrigin', 'preload', 'loop', 'src'])
      assert.equal(audio.crossOrigin, 'anonymous')
      assert.equal(audio.preload, 'auto')
      assert.equal(audio.loop, false)
      assert.equal(audio.src, 'asset://localhost/audio.wav')
    } finally {
      Object.defineProperty(globalThis, 'Audio', {
        configurable: true,
        value: originalAudio,
      })
    }
  })
})

describe('editor audio readiness', () => {
  it('resolves immediately when future audio data is available', async () => {
    const audio = { readyState: 3 } as HTMLAudioElement
    await waitForEditorAudioReady(audio, 1)
  })

  it('waits for canplay instead of treating metadata as playable audio', async () => {
    const listeners = new Map<string, () => void>()
    const audio = {
      readyState: 1,
      addEventListener(name: string, listener: () => void) { listeners.set(name, listener) },
      removeEventListener(name: string) { listeners.delete(name) },
    } as unknown as HTMLAudioElement
    let resolved = false
    const ready = waitForEditorAudioReady(audio, 1000).then(() => { resolved = true })
    await Promise.resolve()
    assert.equal(resolved, false)
    listeners.get('canplay')?.()
    await ready
    assert.equal(resolved, true)
  })
})
