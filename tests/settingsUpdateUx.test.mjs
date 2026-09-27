import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { parse } from 'vue/compiler-sfc'

const path = new URL('../src/views/SettingsView.vue', import.meta.url)
const { descriptor } = parse(readFileSync(path, 'utf8'))
const template = descriptor.template?.content || ''
const script = descriptor.scriptSetup?.content || ''
const style = descriptor.styles.map(item => item.content).join('\n')

test('unsupported builds show a compact manual-update action', () => {
  assert.ok(template.includes('v-if="!updateSupported" class="update-panel__compact-row"'))
  assert.ok(template.includes("openExternalUrl(repoUrl + '/releases/latest')"))
  assert.ok(template.includes("t('settings.updateOpenGitHub')"))
})

test('version comparison and release notes render only for real update metadata', () => {
  assert.ok(template.includes('v-if="updates.latestVersion" class="update-panel__version-flow"'))
  assert.ok(template.includes('v-if="updates.latestVersion && updates.releaseNotes"'))
  assert.ok(!template.includes('updates.latestVersion || appVersion'))
  assert.ok(!template.includes("t('settings.updateNoNotes')"))
})

test('supported update states expose one contextual primary action', () => {
  assert.ok(template.includes("v-if=\"updates.status === 'checking'\""))
  assert.ok(template.includes('v-else-if="updates.requiresManualInstall"'))
  assert.ok(template.includes('v-else-if="updates.hasUpdate"'))
  assert.ok(template.includes(':loading="updateInstalling || updates.isInstallingUpdate"'))
})

test('update overview emphasis and compact layout are state driven', () => {
  assert.ok(script.includes('const updateOverviewEmphasized = computed(() =>'))
  assert.ok(template.includes("'update-panel__overview--emphasis': updateOverviewEmphasized"))
  assert.ok(style.includes('.update-panel__compact-row'))
  assert.ok(style.includes('.update-panel__controls'))
})
