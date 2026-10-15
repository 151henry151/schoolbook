// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors
import { formatEasternTime } from "./time";

test("shows Eastern time in winter and observes daylight saving in summer", () => {
  expect(formatEasternTime("2026-01-15T18:30:00Z")).toBe("Jan 15, 2026, 1:30 PM EST");
  expect(formatEasternTime("2026-07-15T18:30:00Z")).toBe("Jul 15, 2026, 2:30 PM EDT");
});
test("interprets legacy SQLite timestamps as UTC, regardless of the browser timezone", () => {
  expect(formatEasternTime("2026-10-15T21:00:00")).toBe("Oct 15, 2026, 5:00 PM EDT");
  expect(formatEasternTime("2026-10-15T17:00:00-04:00")).toBe("Oct 15, 2026, 5:00 PM EDT");
  expect(formatEasternTime("bad date")).toBe("Unknown time");
});
