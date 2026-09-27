export type InferenceParamMeta = {
  recommendedSampleStep?: number
  source?: string
}

const MAX_INFERENCE_SAMPLE_VALUE = 1_048_576
const INFERENCE_SAMPLE_STEP_MULTIPLIER = 10

export function normalizeInferenceParamMeta(input: unknown): InferenceParamMeta | undefined {
  if (!input || typeof input !== 'object') return undefined
  const source = input as Record<string, unknown>
  const rawStep = Number(source.recommendedSampleStep)
  if (!Number.isFinite(rawStep) || rawStep < 1 || rawStep > MAX_INFERENCE_SAMPLE_VALUE) return undefined
  const recommendedSampleStep = Math.floor(rawStep)
  const rawSource = typeof source.source === 'string' ? source.source.trim() : ''
  return {
    recommendedSampleStep,
    ...(rawSource ? { source: rawSource } : {}),
  }
}

export function resolveInferenceSampleStep(meta: InferenceParamMeta | undefined, fallback: number) {
  const normalized = normalizeInferenceParamMeta(meta)
  if (!normalized?.recommendedSampleStep) return fallback
  const scaled = normalized.recommendedSampleStep * INFERENCE_SAMPLE_STEP_MULTIPLIER
  return scaled <= MAX_INFERENCE_SAMPLE_VALUE ? scaled : normalized.recommendedSampleStep
}

export function alignInferenceStepChange(
  current: number | null,
  next: number | null,
  alignmentStep: number | undefined,
  controlStep: number,
) {
  if (
    typeof current !== 'number'
    || !Number.isFinite(current)
    || typeof next !== 'number'
    || !Number.isFinite(next)
    || typeof alignmentStep !== 'number'
    || !Number.isFinite(alignmentStep)
    || alignmentStep < 1
    || current % alignmentStep === 0
  ) {
    return next
  }
  const delta = next - current
  if (Math.abs(delta) !== controlStep) return next
  return delta > 0
    ? Math.ceil(current / alignmentStep) * alignmentStep
    : Math.floor(current / alignmentStep) * alignmentStep
}
