// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

export const SAMPLE_RATE = 16000;
export const SILENCE_END_MS = 1500;
export const HOLD_MS = 5000;

const ID = /^[A-Za-z0-9_-]+$/;

export function holdComplete(elapsedMs: number): boolean {
  return elapsedMs >= HOLD_MS;
}

export function silenceEndsTurn(silentMs: number): boolean {
  return silentMs >= SILENCE_END_MS;
}

export function embedUrl(videoId: string): string {
  if (!ID.test(videoId)) {
    throw new Error("video id must stay a YouTube id");
  }
  return `https://www.youtube-nocookie.com/embed/${videoId}?rel=0&controls=0&modestbranding=1&iv_load_policy=3`;
}

export const OFFLINE_APPS = ["GCompris", "Tux Paint", "KTurtle", "Stellarium", "Marble"];
