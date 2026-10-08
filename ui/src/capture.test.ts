// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { embedUrl, holdComplete, playerCommand, silenceEndsTurn, songUrl, startEmbeddedPlayer } from "./capture";

test("the parent hold is five seconds and silence ends a turn at 1.5 seconds", () => {
  expect(holdComplete(4999)).toBe(false);
  expect(holdComplete(5000)).toBe(true);
  expect(silenceEndsTurn(1500)).toBe(true);
});

test("video embeds stay on the nocookie domain without player controls", () => {
  const url = embedUrl("abcdefghijk");
  expect(url.startsWith("https://www.youtube-nocookie.com/embed/abcdefghijk")).toBe(true);
  expect(url).toContain("rel=0");
  expect(url).toContain("controls=0");
  expect(url).toContain("autoplay=1");
  expect(url).toContain("enablejsapi=1");
  expect(url).toContain("origin=");
  expect(() => embedUrl("https://evil.example")).toThrow();
});

test("startEmbeddedPlayer unmutes then plays", () => {
  const target = { postMessage: vi.fn() };
  startEmbeddedPlayer(target);
  expect(target.postMessage).toHaveBeenNthCalledWith(
    1,
    JSON.stringify({ event: "command", func: "unMute", args: [] }),
    "https://www.youtube-nocookie.com",
  );
  expect(target.postMessage).toHaveBeenNthCalledWith(
    2,
    JSON.stringify({ event: "command", func: "setVolume", args: [100] }),
    "https://www.youtube-nocookie.com",
  );
  expect(target.postMessage).toHaveBeenNthCalledWith(
    3,
    JSON.stringify({ event: "command", func: "playVideo", args: [] }),
    "https://www.youtube-nocookie.com",
  );
  playerCommand(target, "pauseVideo");
});

test("songs use a local audio path", () => {
  expect(songUrl("songid11111")).toBe("/songs/songid11111");
  expect(() => songUrl("https://evil.example")).toThrow();
});
