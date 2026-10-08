// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

export type AudioPlayer = {
  play: (turnId: string, pcm: Int16Array, sampleRate: number) => Promise<void>;
  stop: () => void;
};

export function decodePcm16(b64: string): Int16Array {
  const raw = atob(b64);
  const bytes = new Uint8Array(raw.length);
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
}

export class PlaybackQueue {
  private active: string | null = null;
  private ignored = new Set<string>();
  private tail: Promise<void> = Promise.resolve();

  constructor(private readonly player: AudioPlayer) {}

  async enqueue(turnId: string, pcm: Int16Array, sampleRate: number): Promise<void> {
    this.tail = this.tail.then(async () => {
      if (this.ignored.has(turnId)) return;
      this.active = turnId;
      await this.player.play(turnId, pcm, sampleRate);
    });
    return this.tail;
  }

  interrupt(): void {
    if (this.active) this.ignored.add(this.active);
    this.active = null;
    this.player.stop();
  }
}

export function webAudioPlayer(): AudioPlayer {
  let context: AudioContext | null = null;
  let current: AudioBufferSourceNode | null = null;
  return {
    async play(_turnId: string, pcm: Int16Array, sampleRate: number) {
      context ??= new AudioContext();
      await context.resume();
      const buffer = context.createBuffer(1, Math.max(pcm.length, 1), sampleRate);
      const data = buffer.getChannelData(0);
      for (let index = 0; index < pcm.length; index += 1) data[index] = pcm[index] / 32768;
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      current = source;
      await new Promise<void>((resolve) => {
        source.onended = () => resolve();
        source.start();
      });
    },
    stop() {
      try {
        current?.stop();
      } catch {
        /* already stopped */
      }
      current = null;
      if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
    },
  };
}
