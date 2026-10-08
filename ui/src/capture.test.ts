// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { embedUrl, holdComplete, silenceEndsTurn } from "./capture";

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
  expect(() => embedUrl("https://evil.example")).toThrow();
});
