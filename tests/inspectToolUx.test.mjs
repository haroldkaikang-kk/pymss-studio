import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { parse } from 'vue/compiler-sfc'

function descriptor(path) {
  return parse(readFileSync(new URL(path, import.meta.url), 'utf8')).descriptor
}

const inspect = descriptor('../src/features/audio-tools/tools/inspect/InspectTool.vue')
const panel = descriptor('../src/features/audio-tools/shared/AudioToolPanel.vue')
const status = descriptor('../src/components/tools/AudioToolStatus.vue')
const inspectTemplate = inspect.template?.content || ''
const inspectScript = inspect.scriptSetup?.content || ''
const panelTemplate = panel.template?.content || ''
const panelScript = panel.scriptSetup?.content || ''
const statusTemplate = status.template?.content || ''
const statusScript = status.scriptSetup?.content || ''

test('inspect keeps file selection and its primary action in one compact row', () => {
  assert.ok(inspectTemplate.includes('hide-idle-status compact-result'))
  assert.ok(inspectTemplate.includes('class="audio-tool-path"'))
  assert.ok(inspectTemplate.includes("t('tools.startInspect')"))
  assert.ok(inspectTemplate.includes('class="inspect-privacy"'))
  assert.ok(!inspectTemplate.includes('<n-alert'))
  assert.ok(!inspectTemplate.includes('class="audio-tool-actions"'))
  assert.ok(inspectScript.includes('inputPath.value = path; await inspect(path)'))
})

test('audio tool panel can hide a status card until work starts', () => {
  assert.ok(panelScript.includes('const showStatusPanel = computed(() =>'))
  assert.ok(panelTemplate.includes('v-if="showStatusPanel" class="audio-tool-card audio-tool-card--side"'))
  assert.ok(panelTemplate.includes(':compact="compactResult"'))
})

test('compact status keeps errors visible but hides successful boilerplate and logs', () => {
  assert.ok(statusScript.includes('const showStatusOverview = computed(() =>'))
  assert.ok(statusScript.includes('const showActivityPanel = computed(() => !props.compact || Boolean(props.error))'))
  assert.ok(statusTemplate.includes('v-if="showStatusOverview"'))
  assert.ok(statusTemplate.includes('v-if="showActivityPanel" class="activity-panel"'))
})
