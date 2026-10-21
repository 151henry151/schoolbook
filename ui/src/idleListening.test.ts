// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors
import { IdleListening } from "./idleListening";

test("pauses after ten seconds of continuous quiet", () => {
  const idle = new IdleListening();
  expect(idle.frame(9900, false, false)).toBe(false);
  expect(idle.frame(100, false, false)).toBe(true);
});

test("speech and processing each give the child a fresh window", () => {
  const idle = new IdleListening();
  idle.frame(9900, false, false);
  expect(idle.frame(30000, true, false)).toBe(false);
  expect(idle.frame(9900, false, false)).toBe(false);
  expect(idle.frame(60000, false, true)).toBe(false);
  expect(idle.frame(9900, false, false)).toBe(false);
  expect(idle.frame(100, false, false)).toBe(true);
  idle.reset();
  expect(idle.frame(100, false, false)).toBe(false);
});
