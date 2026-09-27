<script setup lang="ts">
import { computed } from 'vue'
import type { AudioToolKey, AudioToolResult } from '../types'
import AudioToolStatus from '@/components/tools/AudioToolStatus.vue'
import { useAudioToolRuntime } from '../runtime'

const props = withDefaults(defineProps<{
  tool: AudioToolKey
  statusTitle: string
  statusHint: string
  layout?: 'split' | 'stacked'
  hideIdleStatus?: boolean
  compactResult?: boolean
}>(), {
  layout: 'split',
  hideIdleStatus: false,
  compactResult: false,
})
const runtime = useAudioToolRuntime()
const state = runtime.stateFor(props.tool)
const showStatusPanel = computed(() => {
  const value = state.value
  return !props.hideIdleStatus
    || value.busy
    || value.hasResult
    || Boolean(value.error)
    || value.progress.phase === 'cancelled'
})
</script>

<template>
  <div
    class="audio-tool-layout"
    :class="{ 'audio-tool-layout--stacked': layout === 'stacked' }"
  >
    <section class="audio-tool-card audio-tool-card--main">
      <slot :state="state" />
    </section>
    <aside v-if="showStatusPanel" class="audio-tool-card audio-tool-card--side">
      <h3>{{ statusTitle }}</h3>
      <p>{{ statusHint }}</p>
      <AudioToolStatus
        :busy="state.busy"
        :cancelling="state.cancelling"
        :has-result="state.hasResult"
        :error="state.error"
        :progress="state.progress"
        :percentage="state.percentage"
        :result="state.result"
        :elapsed-ms="state.elapsedMs"
        :logs="state.logs"
        :compact="compactResult"
        @cancel="runtime.cancel"
        @reveal="runtime.revealPath"
      >
        <template v-if="$slots.result" #result="slotProps: { result: AudioToolResult }">
          <slot name="result" :result="slotProps.result" />
        </template>
      </AudioToolStatus>
    </aside>
  </div>
</template>
