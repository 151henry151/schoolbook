// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

export const SAMPLE_RATE = 16000;
export const VOICE_THRESHOLD = 500;
export const VOICE_HOLD = 220;

export function rms16(pcm: Int16Array): number {
  if (pcm.length === 0) return 0;
  let sum = 0;
  for (const sample of pcm) sum += sample * sample;
  return Math.sqrt(sum / pcm.length);
}

export function voiced(pcm: Int16Array, threshold: number = VOICE_THRESHOLD): boolean {
  return rms16(pcm) >= threshold;
}

export function createVad(start: number = VOICE_THRESHOLD, hold: number = VOICE_HOLD) {
  let open = false;
  return (pcm: Int16Array): boolean => {
    const energy = rms16(pcm);
    open = energy >= (open ? hold : start);
    return open;
  };
}

export function floatToPcm16(input: Float32Array): Int16Array {
  const pcm = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index] ?? 0));
    pcm[index] = sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767);
  }
  return pcm;
}

export function downsample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const length = Math.floor(input.length / ratio);
  const output = new Float32Array(length);
  for (let index = 0; index < length; index += 1) {
    output[index] = input[Math.floor(index * ratio)] ?? 0;
  }
  return output;
}

export function encodePcm16(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}
