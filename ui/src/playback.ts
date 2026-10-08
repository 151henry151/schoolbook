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
  private turnId: string | null = null;
  private queuedMs = 0;
  private playedMs = 0;
  private progress: ((elapsedMs: number, durationMs: number) => void) | null = null;
  private pending = 0;
  private epoch = 0;

  constructor(private readonly player: AudioPlayer) {}

  isIdle(): boolean {
    return this.pending === 0;
  }

  setProgress(handler: ((elapsedMs: number, durationMs: number) => void) | null): void {
    this.progress = handler;
  }

  async enqueue(turnId: string, pcm: Int16Array, sampleRate: number): Promise<void> {
    const epoch = this.epoch;
    if (this.turnId !== turnId) {
      this.turnId = turnId;
      this.queuedMs = 0;
      this.playedMs = 0;
    }
    const chunkMs = (pcm.length / Math.max(sampleRate, 1)) * 1000;
    this.queuedMs += chunkMs;
    this.pending += 1;
    this.tail = this.tail.then(async () => {
      try {
        if (epoch !== this.epoch || this.ignored.has(turnId)) return;
        this.active = turnId;
        const begun = Date.now();
        const tick = globalThis.setInterval(() => {
          const elapsed = this.playedMs + Math.min(Date.now() - begun, chunkMs);
          this.progress?.(elapsed, this.queuedMs);
        }, 40);
        try {
          this.progress?.(this.playedMs, this.queuedMs);
          await this.player.play(turnId, pcm, sampleRate);
        } finally {
          globalThis.clearInterval(tick);
          this.playedMs += chunkMs;
          this.progress?.(this.playedMs, this.queuedMs);
        }
      } finally {
        if (epoch === this.epoch) this.pending = Math.max(0, this.pending - 1);
        this.active = null;
      }
    });
    return this.tail;
  }

  interrupt(): void {
    this.epoch += 1;
    this.active = null;
    this.queuedMs = 0;
    this.playedMs = 0;
    this.pending = 0;
    this.tail = Promise.resolve();
    this.player.stop();
  }

  whenIdle(): Promise<void> {
    return this.tail;
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
