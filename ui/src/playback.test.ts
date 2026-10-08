// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { PlaybackQueue, decodePcm16 } from "./playback";

test("stale chunks from a cancelled turn are dropped", async () => {
  const played: string[] = [];
  const queue = new PlaybackQueue({
    play: async (turnId) => {
      played.push(turnId);
    },
    stop: () => {
      played.push("stop");
    },
  });
  await queue.enqueue("old", decodePcm16("AAA="), 16000);
  queue.interrupt();
  await queue.enqueue("new", decodePcm16("AAA="), 16000);
  expect(played).toContain("stop");
  expect(played).toContain("new");
  expect(played.filter((item) => item === "old")).toHaveLength(1);
});
