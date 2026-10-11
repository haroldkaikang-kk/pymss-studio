/**
 * Create an audio element for editor playback.
 *
 * The CORS mode must be set before assigning `src`. Tauri serves linked
 * assets through its custom asset protocol; WebKit otherwise treats the
 * media request as no-cors and a MediaElementAudioSourceNode outputs silence.
 */
export function createEditorAudioElement(url: string): HTMLAudioElement {
  const audio = new Audio()
  audio.crossOrigin = 'anonymous'
  audio.preload = 'auto'
  audio.loop = false
  audio.src = url
  return audio
}

/**
 * Wait until WebKit has decoded enough media around the requested position to
 * start smoothly. Metadata alone is not sufficient for several local WAV
 * stems started together on older Intel Macs.
 */
export function waitForEditorAudioReady(audio: HTMLAudioElement, timeoutMs = 8000): Promise<void> {
  if (audio.readyState >= 3) return Promise.resolve()
  return new Promise((resolve) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      audio.removeEventListener('canplay', finish)
      audio.removeEventListener('canplaythrough', finish)
      audio.removeEventListener('error', finish)
      resolve()
    }
    const timer = setTimeout(finish, Math.max(0, timeoutMs))
    audio.addEventListener('canplay', finish, { once: true })
    audio.addEventListener('canplaythrough', finish, { once: true })
    audio.addEventListener('error', finish, { once: true })
  })
}
