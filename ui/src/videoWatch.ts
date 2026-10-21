// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

/** Count distinct content actually played, excluding pauses, seeks, and repeated segments. */
export class VideoWatchTracker {
  private last?: { position: number; at: number; state: number };
  private state = -1;
  private duration = 0;
  private rate = 1;
  private ranges: [number, number][] = [];
  private reported = false;

  update(data: unknown, nowMs: number): { watched_s: number; duration_s: number } | null {
    let payload: { event?: string; info?: unknown };
    try { payload = typeof data === "string" ? JSON.parse(data) : data; } catch { return null; }
    if (!payload || !["infoDelivery", "initialDelivery", "onStateChange"].includes(payload.event ?? "")) return null;
    const info = payload.info;
    if (typeof info === "number") {
      this.state = info;
      this.last = undefined;
      return null;
    }
    if (!info || typeof info !== "object") return null;
    const values = info as Record<string, unknown>;
    if (typeof values.duration === "number" && Number.isFinite(values.duration) && values.duration > 0)
      this.duration = values.duration;
    if (typeof values.playbackRate === "number" && values.playbackRate > 0 && values.playbackRate <= 4)
      this.rate = values.playbackRate;
    if (typeof values.playerState === "number") this.state = values.playerState;
    const position = values.currentTime;
    if (typeof position !== "number" || !Number.isFinite(position) || position < 0) {
      if (this.state !== 1) this.last = undefined;
      return null;
    }
    const previous = this.last;
    this.last = { position, at: nowMs, state: this.state };
    if (previous && previous.state === 1 && [0, 1, 2].includes(this.state)) {
      const elapsed = (nowMs - previous.at) / 1000;
      const delta = position - previous.position;
      if (elapsed > 0 && elapsed <= 10 && delta > 0 && delta <= elapsed * this.rate + 0.75) {
        this.ranges.push([previous.position, Math.min(position, this.duration || position)]);
        this.ranges.sort((a, b) => a[0] - b[0]);
        const merged: [number, number][] = [];
        for (const range of this.ranges) {
          const tail = merged[merged.length - 1];
          if (tail && range[0] <= tail[1]) tail[1] = Math.max(tail[1], range[1]);
          else merged.push([...range]);
        }
        this.ranges = merged;
      }
    }
    const watched = this.ranges.reduce((sum, [start, end]) => sum + Math.max(0, end - start), 0);
    if (!this.reported && this.duration > 0 && watched >= this.duration / 2) {
      this.reported = true;
      return { watched_s: watched, duration_s: this.duration };
    }
    return null;
  }
}
