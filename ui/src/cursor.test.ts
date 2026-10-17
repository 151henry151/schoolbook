// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { hideVideoCursor, POINTER_CURSOR, VIDEO_CURSOR_IDLE_MS } from "./cursor";

test("the pointer is a big cartoon arrow with a white center and blue outline", () => {
  const decoded = decodeURIComponent(POINTER_CURSOR);
  expect(POINTER_CURSOR).toContain("cursor: url(");
  expect(decoded).toMatch(/#fff|#ffffff|white/i);
  expect(decoded).toMatch(/#2a6f7f|#1d6fa5|#2080c0/i);
  expect(decoded).toMatch(/48|64/);
});

test("a playing video hides the cursor until the child moves", () => {
  expect(hideVideoCursor(false, true)).toBe(true);
  expect(hideVideoCursor(false, false)).toBe(false);
  expect(hideVideoCursor(true, true)).toBe(false);
  expect(VIDEO_CURSOR_IDLE_MS).toBeGreaterThanOrEqual(1500);
});
