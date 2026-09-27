import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  alignInferenceStepChange,
  normalizeInferenceParamMeta,
  resolveInferenceSampleStep,
} from '../src/features/inference/sampleStep.ts'

describe('inference sample-step metadata', () => {
  it('normalizes positive integer steps and trims their source', () => {
    assert.deepEqual(
      normalizeInferenceParamMeta({ recommendedSampleStep: 512.9, source: ' model.stft_hop_length ' }),
      { recommendedSampleStep: 512, source: 'model.stft_hop_length' },
    )
  })

  it('rejects missing and non-positive steps', () => {
    assert.equal(normalizeInferenceParamMeta(undefined), undefined)
    assert.equal(normalizeInferenceParamMeta({ recommendedSampleStep: 0 }), undefined)
    assert.equal(normalizeInferenceParamMeta({ recommendedSampleStep: Number.NaN }), undefined)
    assert.equal(normalizeInferenceParamMeta({ recommendedSampleStep: 1_048_577 }), undefined)
  })

  it('uses the existing control fallback when metadata is unavailable', () => {
    assert.equal(resolveInferenceSampleStep({ recommendedSampleStep: 441 }, 1024), 4410)
    assert.equal(resolveInferenceSampleStep({ recommendedSampleStep: 512 }, 1024), 5120)
    assert.equal(resolveInferenceSampleStep(undefined, 1024), 1024)
    assert.equal(resolveInferenceSampleStep({ recommendedSampleStep: -1 }, 1), 1)
  })

  it('aligns the first step-button click in the requested direction', () => {
    assert.equal(alignInferenceStepChange(24_000, 28_410, 441, 4_410), 24_255)
    assert.equal(alignInferenceStepChange(24_000, 19_590, 441, 4_410), 23_814)
    assert.equal(alignInferenceStepChange(24_255, 28_665, 441, 4_410), 28_665)
    assert.equal(alignInferenceStepChange(24_000, 25_000, 441, 4_410), 25_000)
  })
})
