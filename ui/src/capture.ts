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

function pageOrigin(): string {
  if (typeof window === "undefined") return "";
  return window.location.origin;
}

export function songUrl(videoId: string): string {
  if (!ID.test(videoId)) {
    throw new Error("video id must stay a YouTube id");
  }
  return `/songs/${videoId}`;
}

export function embedUrl(videoId: string, origin = pageOrigin()): string {
  if (!ID.test(videoId)) {
    throw new Error("video id must stay a YouTube id");
  }
  const originPart = origin ? `&origin=${encodeURIComponent(origin)}` : "";
  return `https://www.youtube-nocookie.com/embed/${videoId}?rel=0&controls=0&modestbranding=1&iv_load_policy=3&autoplay=1&enablejsapi=1${originPart}`;
}

export type PlayerTarget = {
  postMessage: (message: string, origin: string) => void;
};

export type PlayerFunc = "playVideo" | "pauseVideo" | "unMute" | "setVolume";

export function playerCommand(
  target: PlayerTarget | null | undefined,
  func: PlayerFunc,
  args: unknown[] = [],
): void {
  if (!target) return;
  target.postMessage(JSON.stringify({ event: "command", func, args }), "https://www.youtube-nocookie.com");
}

export function startEmbeddedPlayer(target: PlayerTarget | null | undefined): void {
  playerCommand(target, "unMute");
  playerCommand(target, "setVolume", [100]);
  playerCommand(target, "playVideo");
}

export function youtubePlayerReady(data: unknown): boolean {
  let payload = data;
  if (typeof payload === "string") {
    try {
      payload = JSON.parse(payload);
    } catch {
      return false;
    }
  }
  return Boolean(payload && typeof payload === "object" && (payload as { event?: string }).event === "onReady");
}

export const OFFLINE_APPS = ["GCompris", "Tux Paint", "KTurtle", "Stellarium", "Marble"];
