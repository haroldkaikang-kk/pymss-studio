import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import { parse } from 'vue/compiler-sfc'

const viewPath = new URL('../src/views/WorkflowNodeEditorView.vue', import.meta.url)
const viewDescriptor = parse(readFileSync(viewPath, 'utf8')).descriptor
const template = viewDescriptor.template?.content || ''
const script = ts.createSourceFile(
  'WorkflowNodeEditorView.ts',
  viewDescriptor.scriptSetup.content,
  ts.ScriptTarget.Latest,
  true,
)
const names = new Set([
  'snapshot',
  'dirty',
  'captureInitialSnapshot',
  'syncCurrentDefinition',
  'closeEditor',
  'destroyWindow',
  'saveAndClose',
])
const selected = script.statements.filter(statement => (
  ts.isFunctionDeclaration(statement) ? names.has(statement.name?.text)
    : ts.isVariableStatement(statement) && statement.declarationList.declarations.some(item => names.has(item.name.getText(script)))
))
assert.equal(selected.length, names.size)
const code = ts.transpileModule(selected.map(statement => statement.getText(script)).join('\n'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText

const editorPath = new URL('../src/components/workflow/WorkflowNodeEditorLite.vue', import.meta.url)
const editorScript = parse(readFileSync(editorPath, 'utf8')).descriptor.scriptSetup.content

function computed(read) {
  return { get value() { return read() } }
}

function ref(value) {
  return { value }
}

function createContext() {
  const navigation = []
  const warnings = []
  let canvasDefinition = { nodes: [{ id: 1 }], links: [] }
  let saveResult = true
  const context = {
    computed,
    name: ref('Workflow'),
    description: ref(''),
    defaultDevice: ref('auto'),
    defaultFormat: ref('wav'),
    definition: ref(canvasDefinition),
    loaded: ref(true),
    initialSnapshot: ref(''),
    editorRef: ref({ snapshotDefinition: () => canvasDefinition }),
    showClosePrompt: ref(false),
    saving: ref(false),
    formError: ref(''),
    currentWindow: null,
    invoke: async () => {},
    router: { push: async target => navigation.push(target) },
    message: { warning: value => warnings.push(value) },
    save: async () => saveResult,
  }
  const result = vm.runInNewContext(
    `${code}\n({ dirty, captureInitialSnapshot, closeEditor, saveAndClose })`,
    context,
  )
  return {
    context,
    result,
    navigation,
    warnings,
    setCanvasDefinition(value) { canvasDefinition = value },
    setSaveResult(value) { saveResult = value },
  }
}

test('advanced editor exposes the same unsaved-close actions as the simple editor', () => {
  assert.ok(template.includes('ref="editorRef"'))
  assert.ok(template.includes('@initialized="captureInitialSnapshot"'))
  assert.ok(template.includes('v-model:show="showClosePrompt"'))
  assert.ok(template.includes("t('workflows.simpleDiscardChanges')"))
  assert.ok(template.includes("t('workflows.simpleSaveAndClose')"))
  assert.ok(editorScript.includes('defineExpose({ snapshotDefinition })'))
  assert.ok(editorScript.includes("emit('initialized')"))
})

test('advanced editor flushes the live canvas before deciding whether to close', async () => {
  const state = createContext()
  state.result.captureInitialSnapshot()
  assert.equal(state.result.dirty.value, false)

  state.setCanvasDefinition({ nodes: [{ id: 1 }, { id: 2 }], links: [] })
  await state.result.closeEditor()

  assert.equal(state.result.dirty.value, true)
  assert.equal(state.context.showClosePrompt.value, true)
  assert.deepEqual(state.navigation, [])
})

test('advanced editor closes only after a successful save and keeps invalid drafts open', async () => {
  const state = createContext()
  state.result.captureInitialSnapshot()
  state.setCanvasDefinition({ nodes: [{ id: 1 }, { id: 2 }], links: [] })
  state.context.showClosePrompt.value = true

  state.setSaveResult(false)
  await state.result.saveAndClose()
  assert.deepEqual(state.navigation, [])

  state.context.showClosePrompt.value = true
  state.context.formError.value = 'invalid workflow'
  await state.result.saveAndClose()
  assert.deepEqual(state.navigation, [])
  assert.deepEqual(state.warnings, ['invalid workflow'])
  assert.equal(state.context.showClosePrompt.value, true)

  state.context.formError.value = ''
  state.setSaveResult(true)
  await state.result.saveAndClose()
  assert.deepEqual(state.navigation, ['/workflows'])
})
