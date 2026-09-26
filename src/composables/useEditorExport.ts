import { computed, ref } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import type { MessageApiInjection } from 'naive-ui/es/message/src/MessageProvider'
import type { ComposerTranslation } from 'vue-i18n'
import type { EditorExportFormat, EditorExportSampleRate } from '@/types/editor'
import type { useEditorStore } from '@/stores/editor'
import { EditorExportCancelledError } from '@/stores/editor'
import type { useSettingsStore } from '@/stores/settings'

type EditorStore = ReturnType<typeof useEditorStore>
type SettingsStore = ReturnType<typeof useSettingsStore>

type UseEditorExportOptions = {
  editor: EditorStore
  settings: SettingsStore
  message: MessageApiInjection
  t: ComposerTranslation
}

export function useEditorExport(options: UseEditorExportOptions) {
  const { editor, settings, message, t } = options

  const showExportDialog = ref(false)
  const exportFormatDraft = ref<EditorExportFormat>('wav')
  const exportWavBitDepthDraft = ref('PCM_24')
  const exportFlacBitDepthDraft = ref('PCM_24')
  const exportSampleRateDraft = ref<EditorExportSampleRate>('auto')
  const exportPeakProtectionDraft = ref(true)
  const exportFileNameDraft = ref('')
  const exportDirDraft = ref('')
  const exportDirPicking = ref(false)
  const exportProgressPercentage = computed(() => {
    const progress = editor.exportProgress
    return progress ? Math.min(100, Math.round(progress.completed / Math.max(1, progress.total) * 100)) : 0
  })
  const exportProgressText = computed(() => {
    const progress = editor.exportProgress
    if (!progress) return ''
    const phase = progress.phase === 'rendering'
      ? t('editor.exportPhaseRendering')
      : progress.phase === 'finalizing'
        ? t('editor.exportPhaseFinalizing')
        : progress.phase === 'writing'
          ? t('editor.exportPhaseWriting')
          : progress.phase === 'completed'
            ? t('editor.exportPhaseCompleted')
            : t('editor.exportPhasePreparing')
    return progress.current ? `${phase} · ${progress.current}` : phase
  })

  function getDefaultExportDir() {
    return settings.outputDir.trim() || ''
  }

  function openExportDialog() {
    exportFormatDraft.value = editor.exportFormat
    exportWavBitDepthDraft.value = settings.wavBitDepth
    exportFlacBitDepthDraft.value = settings.flacBitDepth
    const projectName = String(editor.session?.name || editor.session?.id || 'editor').trim()
    exportFileNameDraft.value = `${projectName || 'editor'}_mix`
    exportDirDraft.value = editor.lastExport?.path
      ? editor.lastExport.path.replace(/[\\/][^\\/]+$/, '')
      : getDefaultExportDir()
    showExportDialog.value = true
  }

  function closeExportDialog() {
    showExportDialog.value = false
  }

  function setExportDialogVisible(value: boolean) {
    if (!value) closeExportDialog()
  }

  function setExportFormat(value: EditorExportFormat) {
    exportFormatDraft.value = value
  }

  function setExportWavBitDepth(value: string) {
    exportWavBitDepthDraft.value = value
  }

  function setExportFlacBitDepth(value: string) {
    exportFlacBitDepthDraft.value = value
  }

  function setExportSampleRate(value: EditorExportSampleRate) {
    exportSampleRateDraft.value = value
  }

  function setExportPeakProtection(value: boolean) {
    exportPeakProtectionDraft.value = value
  }

  function setExportFileName(value: string) {
    exportFileNameDraft.value = value
  }

  function setExportDir(value: string) {
    exportDirDraft.value = value
  }

  async function pickExportDir() {
    exportDirPicking.value = true
    try {
      const folder = await invoke<string | null>('pick_output_folder')
      if (folder) exportDirDraft.value = folder
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('editor.exportDirPickFailed'))
    } finally {
      exportDirPicking.value = false
    }
  }

  async function exportMix() {
    try {
      const peakProtection = exportFormatDraft.value !== 'wav'
        || exportWavBitDepthDraft.value !== 'FLOAT'
        || exportPeakProtectionDraft.value
      const result = await editor.exportMix({
        format: exportFormatDraft.value,
        exportDir: exportDirDraft.value.trim() || undefined,
        fileName: exportFileNameDraft.value.trim() || undefined,
        audioParams: {
          wavBitDepth: exportWavBitDepthDraft.value,
          flacBitDepth: exportFlacBitDepthDraft.value,
          sampleRate: exportSampleRateDraft.value,
          peakProtection,
        },
      })
      editor.exportFormat = exportFormatDraft.value
      settings.wavBitDepth = exportWavBitDepthDraft.value
      settings.flacBitDepth = exportFlacBitDepthDraft.value
      message.success(t('editor.exported', { path: result.path }))
      if (result.peakProtectionApplied && Number(result.peakAdjustmentDb) < 0) {
        message.info(t('editor.exportPeakAdjusted', {
          db: Math.abs(Number(result.peakAdjustmentDb)).toFixed(1),
        }))
      }
      try {
        await invoke('reveal_path', { path: result.path })
      } catch {
        message.warning(t('editor.exportOpenFailed'))
      }
      closeExportDialog()
    } catch (error) {
      if (error instanceof EditorExportCancelledError) message.info(t('editor.exportCancelled'))
      else message.error(editor.lastError || t('editor.exportFailed'))
    }
  }

  async function cancelExport() {
    try {
      await editor.cancelExport()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('editor.exportCancelFailed'))
    }
  }

  return {
    showExportDialog,
    exportFormatDraft,
    exportWavBitDepthDraft,
    exportFlacBitDepthDraft,
    exportSampleRateDraft,
    exportPeakProtectionDraft,
    exportFileNameDraft,
    exportDirDraft,
    exportDirPicking,
    exportProgressPercentage,
    exportProgressText,
    openExportDialog,
    closeExportDialog,
    setExportDialogVisible,
    setExportFormat,
    setExportWavBitDepth,
    setExportFlacBitDepth,
    setExportSampleRate,
    setExportPeakProtection,
    setExportFileName,
    setExportDir,
    pickExportDir,
    exportMix,
    cancelExport,
  }
}
