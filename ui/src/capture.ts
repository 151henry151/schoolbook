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
  return `https://www.youtube-nocookie.com/embed/${videoId}?rel=0&controls=0&modestbranding=1&iv_load_policy=3&autoplay=1&mute=1&enablejsapi=1${originPart}`;
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

export function startEmbeddedPlayer(target: PlayerTarget | null | undefined, volume = 100): void {
  playerCommand(target, "setVolume", [volume]);
  playerCommand(target, "unMute");
  playerCommand(target, "playVideo");
}

function youtubePlayerPayload(data: unknown): { event?: string; info?: unknown } | null {
  let payload = data;
  if (typeof payload === "string") {
    try {
      payload = JSON.parse(payload);
    } catch {
      return null;
    }
  }
  if (!payload || typeof payload !== "object") return null;
  return payload as { event?: string; info?: unknown };
}

export function youtubePlayerReady(data: unknown): boolean {
  const payload = youtubePlayerPayload(data);
  return Boolean(payload && payload.event === "onReady");
}

export function youtubePlayerEnded(data: unknown): boolean {
  const payload = youtubePlayerPayload(data);
  if (!payload) return false;
  if (payload.event === "initialDelivery") return false;
  const info = payload.info;
  if (info === 0) return payload.event === "onStateChange" || payload.event === "infoDelivery";
  if (info && typeof info === "object" && (info as { playerState?: unknown }).playerState === 0) {
    return payload.event === "onStateChange" || payload.event === "infoDelivery";
  }
  return false;
}

export const OFFLINE_APPS = ["GCompris", "Tux Paint", "KTurtle", "Stellarium", "Marble"];
