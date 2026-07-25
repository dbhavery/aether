// Tiny pure-TS WAV encoder for Voice V1 step 5 push-to-talk capture.
//
// The browser's MediaRecorder defaults emit WebM/Opus (or platform-
// specific formats); whisper.cpp wants PCM WAV. Rather than pull in
// a heavy dependency, we decode the captured audio through a
// WebAudio `OfflineAudioContext` and then serialize the Float32
// channel data to a 16-bit linear PCM WAV blob in this helper.
//
// Shape: 16 kHz mono, 16-bit little-endian PCM, RIFF/WAVE header.
// The sample rate matches what `docs/VOICE-V1-ARCHITECTURE.md`
// recommends and what whisper expects natively.
//
// This module is deliberately pure — no DOM, no WebAudio calls —
// so it can be unit-tested without a browser.

/**
 * Encode an interleaved or single-channel Float32 PCM buffer into a
 * RIFF/WAVE byte sequence.
 *
 * - `samples` values in `[-1, 1]` get clipped; anything outside is
 *   clamped before conversion so no wraparound noise leaks into the
 *   16-bit output.
 * - `sampleRate` must be > 0. Voice V1 pins to 16000 Hz.
 * - `channels` must be 1 or 2. Voice V1 pins to 1 (mono).
 *
 * Returns a `Uint8Array` — callers wrap it in a `Blob` or base64-
 * encode it as needed.
 */
export function encodeWav(
  samples: Float32Array,
  sampleRate: number,
  channels: number,
): Uint8Array {
  if (!Number.isFinite(sampleRate) || sampleRate <= 0) {
    throw new Error(`encodeWav: sampleRate must be > 0 (got ${sampleRate})`);
  }
  if (channels !== 1 && channels !== 2) {
    throw new Error(`encodeWav: channels must be 1 or 2 (got ${channels})`);
  }
  const bitDepth = 16;
  const bytesPerSample = bitDepth / 8;
  const blockAlign = channels * bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataSize = samples.length * bytesPerSample;
  const bufferSize = 44 + dataSize;
  const buffer = new ArrayBuffer(bufferSize);
  const view = new DataView(buffer);

  // RIFF header
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(view, 8, "WAVE");

  // fmt chunk
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true); // PCM subchunk size
  view.setUint16(20, 1, true); // audio format = PCM
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);

  // data chunk
  writeAscii(view, 36, "data");
  view.setUint32(40, dataSize, true);

  // PCM samples
  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    const intVal = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    view.setInt16(offset, Math.round(intVal), true);
    offset += 2;
  }

  return new Uint8Array(buffer);
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let i = 0; i < value.length; i++) {
    view.setUint8(offset + i, value.charCodeAt(i));
  }
}

/**
 * Base64-encode a byte buffer without splitting surrogates. The
 * naive `btoa(String.fromCharCode(...bytes))` pattern blows up on
 * long buffers (argument-count limits) and misencodes values >= 128.
 * This helper chunks through the buffer in small slices, building
 * the latin1 string fragment-by-fragment, then calls `btoa` once at
 * the end.
 */
export function bytesToBase64(bytes: Uint8Array): string {
  const chunkSize = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const slice = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...slice);
  }
  // Fallback for non-browser test envs: btoa may be unavailable.
  if (typeof btoa === "function") {
    return btoa(binary);
  }
  // Node-style base64 via Buffer if present.
  const g = globalThis as unknown as {
    Buffer?: { from(input: string, enc: string): { toString(enc: string): string } };
  };
  if (g.Buffer) {
    return g.Buffer.from(binary, "binary").toString("base64");
  }
  throw new Error("bytesToBase64: no base64 encoder available");
}

/**
 * Convenience wrapper — encode `samples` to WAV and wrap the result
 * in a `data:audio/wav;base64,...` URL suitable for the
 * `transcribe_utterance` Tauri command.
 */
export function pcmToWavDataUrl(
  samples: Float32Array,
  sampleRate: number,
  channels: number,
): string {
  const wav = encodeWav(samples, sampleRate, channels);
  return `data:audio/wav;base64,${bytesToBase64(wav)}`;
}
