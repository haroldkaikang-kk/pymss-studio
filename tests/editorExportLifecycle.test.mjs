import assert from 'node:assert/strict'
import test, { after, afterEach } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { createPinia } from 'pinia'

const vite = await createServer({
  configFile: false,
  server: { watch: null, middlewareMode: true, hmr: false, preTransformRequests: false },
  appType: 'custom',
  optimizeDeps: { noDiscovery: true },
  resolve: { alias: { '@': fileURLToPath(new URL('../src', import.meta.url)) } },
})
after(() => vite.close())

globalThis.window = {
  matchMedia: () => ({ matches: false }),
  addEventListener() {},
  removeEventListener() {},
}
Object.defineProperty(globalThis, 'navigator', {
  value: { language: 'en' },
  configurable: true,
})
const { useEditorStore, EditorExportCancelledError } = await vite.ssrLoadModule('/src/stores/editor.ts')
const stores = []
const flush = async () => { await new Promise(resolve => setImmediate(resolve)) }

function deferred() {
  let resolve
  let reject
  const promise = new Promise((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

function environment({ startGate, cancelAccepted = true } = {}) {
  const callbacks = new Map()
  const listeners = new Map()
  const calls = []
  let callbackId = 0
  globalThis.window = {
    __TAURI_INTERNALS__: {
      transformCallback(handler) { callbacks.set(++callbackId, handler); return callbackId },
      async invoke(command, args) {
        if (command === 'plugin:event|listen') {
          listeners.set(args.handler, { event: args.event, handler: callbacks.get(args.handler) })
          return args.handler
        }
        if (command === 'plugin:event|unlisten') {
          listeners.delete(args.eventId)
          return null
        }
        calls.push({ command, args })
        if (command === 'start_editor_mix_export') {
          if (startGate) await startGate.promise
          return { taskId: args.payload.taskId, started: true }
        }
        if (command === 'cancel_editor_mix_export') {
          if (cancelAccepted) {
            dispatch('pymss://worker-event', {
              type: 'task_cancelled', taskId: args.taskId, payload: { message: 'Cancelled' },
            })
          }
          return cancelAccepted
        }
        throw new Error(`Unexpected IPC command: ${command}`)
      },
    },
    __TAURI_EVENT_PLUGIN_INTERNALS__: { unregisterListener() {} },
  }

  function dispatch(event, payload) {
    for (const listener of listeners.values()) {
      if (listener.event === event) listener.handler({ event, payload })
    }
  }

  const store = useEditorStore(createPinia())
  stores.push(store)
  store.session = {
    id: 'project',
    name: 'Project',
    masterVolume: 1,
    masterPan: 0,
    sources: [{
      id: 'source', role: 'stem', path: 'D:/audio.wav', name: 'audio.wav',
      duration: 1, sampleRate: 48000, channels: 2, missing: false,
    }],
    tracks: [{
      id: 'track', sourceId: 'source', role: 'stem', name: 'Track', volume: 1,
      pan: 0, muted: false, solo: false, fadeIn: 0, fadeOut: 0,
    }],
    createdAt: 1,
    updatedAt: 1,
  }
  return { store, calls, dispatch }
}

afterEach(() => {
  for (const store of stores.splice(0)) store.$dispose()
  Reflect.deleteProperty(globalThis, 'window')
})

test('background editor export publishes progress and resolves its terminal result', async () => {
  const env = environment()
  const exporting = env.store.exportMix({ format: 'wav' })
  await flush()
  const start = env.calls.find(call => call.command === 'start_editor_mix_export')
  assert.ok(start)
  const taskId = start.args.payload.taskId

  env.dispatch('pymss://worker-event', {
    type: 'editor_export_progress', taskId,
    payload: { phase: 'rendering', completed: 54, total: 100, current: 'audio.wav' },
  })
  assert.equal(env.store.exportProgress.completed, 54)
  assert.equal(env.store.exportProgress.current, 'audio.wav')
  env.dispatch('pymss://worker-event', {
    type: 'editor_mix_exported', taskId,
    payload: { path: 'D:/mix.wav', duration: 1, sampleRate: 48000, channels: 2, format: 'wav' },
  })

  const result = await exporting
  assert.equal(result.path, 'D:/mix.wav')
  assert.equal(env.store.exporting, false)
  assert.equal(env.store.lastExport.path, 'D:/mix.wav')
})

test('cancellation requested before the start ACK waits before terminating the worker', async () => {
  const startGate = deferred()
  const env = environment({ startGate })
  const exporting = env.store.exportMix({ format: 'wav' })
  await flush()
  const cancelling = env.store.cancelExport()
  await flush()
  assert.equal(env.calls.filter(call => call.command === 'cancel_editor_mix_export').length, 0)

  startGate.resolve()
  assert.equal(await cancelling, true)
  await assert.rejects(exporting, EditorExportCancelledError)
  assert.equal(env.calls.filter(call => call.command === 'cancel_editor_mix_export').length, 1)
  assert.equal(env.store.exporting, false)
})

test('cancellation during listener initialization prevents the worker from starting', async () => {
  const env = environment()
  const exporting = env.store.exportMix({ format: 'wav' })
  assert.equal(await env.store.cancelExport(), true)

  await assert.rejects(exporting, EditorExportCancelledError)
  assert.equal(env.calls.filter(call => call.command === 'start_editor_mix_export').length, 0)
  assert.equal(env.store.exporting, false)
})

test('a late cancellation cannot replace an already accepted completion event', async () => {
  const env = environment({ cancelAccepted: false })
  const exporting = env.store.exportMix({ format: 'wav' })
  await flush()
  const start = env.calls.find(call => call.command === 'start_editor_mix_export')
  const taskId = start.args.payload.taskId

  assert.equal(await env.store.cancelExport(), false)
  env.dispatch('pymss://worker-event', {
    type: 'editor_mix_exported', taskId,
    payload: { path: 'D:/mix.wav', duration: 1, sampleRate: 48000, channels: 2, format: 'wav' },
  })

  const result = await exporting
  assert.equal(result.path, 'D:/mix.wav')
  assert.equal(env.store.lastError, null)
})
