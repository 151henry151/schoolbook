// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { PlaybackQueue, decodePcm16 } from "./playback";

test("playback reports elapsed time against the queued turn", async () => {
  let finish = () => {};
  const playing = new Promise<void>((resolve) => {
    finish = resolve;
  });
  const seen: Array<[number, number]> = [];
  const queue = new PlaybackQueue({
    play: async () => playing,
    stop: () => {},
  });
  queue.setProgress((elapsed, duration) => {
    seen.push([elapsed, duration]);
  });
  const started = queue.enqueue("live", new Int16Array(24000), 24000);
  await vi.waitFor(() => expect(seen.length).toBeGreaterThan(0));
  expect(seen[0][1]).toBeGreaterThanOrEqual(1000);
  finish();
  await started;
});

test("isIdle is false while a chunk is playing", async () => {
  let finish = () => {};
  const playing = new Promise<void>((resolve) => {
    finish = resolve;
  });
  const queue = new PlaybackQueue({
    play: async () => playing,
    stop: () => {},
  });
  expect(queue.isIdle()).toBe(true);
  const started = queue.enqueue("live", decodePcm16("AAA="), 16000);
  expect(queue.isIdle()).toBe(false);
  finish();
  await started;
  expect(queue.isIdle()).toBe(true);
});

test("whenIdle waits until queued audio finishes", async () => {
  let finish = () => {};
  const playing = new Promise<void>((resolve) => {
    finish = resolve;
  });
  const queue = new PlaybackQueue({
    play: async () => playing,
    stop: () => {},
  });
  const started = queue.enqueue("live", decodePcm16("AAA="), 16000);
  let idle = false;
  void queue.whenIdle().then(() => {
    idle = true;
  });
  await Promise.resolve();
  expect(idle).toBe(false);
  finish();
  await started;
  await queue.whenIdle();
  expect(idle).toBe(true);
});

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
