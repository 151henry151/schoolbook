// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors
import { VideoWatchTracker } from './videoWatch';

function sample(tracker: VideoWatchTracker, position: number, time: number, state = 1, duration = 100) {
  return tracker.update({ event: 'infoDelivery', info: { currentTime: position, duration, playerState: state } }, time * 1000);
}

test('counts only after half of the video plays and reports once', () => {
  const tracker = new VideoWatchTracker();
  for (let n = 0; n < 50; n++) expect(sample(tracker, n, n)).toBeNull();
  expect(sample(tracker, 50, 50)).toEqual({ watched_s: 50, duration_s: 100 });
  expect(sample(tracker, 51, 51)).toBeNull();
});

test('seeking past halfway does not count skipped content', () => {
  const tracker = new VideoWatchTracker();
  sample(tracker, 0, 0);
  for (let n = 1; n <= 10; n++) sample(tracker, n, n);
  expect(sample(tracker, 70, 11)).toBeNull();
  for (let n = 71; n <= 100; n++) expect(sample(tracker, n, n - 59)).toBeNull();
});

test('paused time and replaying the same segment do not add coverage', () => {
  const tracker = new VideoWatchTracker();
  for (let n = 0; n <= 30; n++) sample(tracker, n, n);
  for (let n = 31; n <= 100; n++) expect(sample(tracker, 30, n, 2)).toBeNull();
  for (let n = 0; n <= 49; n++) expect(sample(tracker, n, 101 + n)).toBeNull();
  expect(sample(tracker, 50, 151)).toEqual({ watched_s: 50, duration_s: 100 });
});

test('unknown duration, invalid messages, and buffering do not count', () => {
  const tracker = new VideoWatchTracker();
  expect(tracker.update('bad json', 0)).toBeNull();
  for (let n = 0; n <= 100; n++) expect(sample(tracker, n, n, 3)).toBeNull();
  expect(sample(tracker, Infinity, 101)).toBeNull();
  const unknown = new VideoWatchTracker();
  for (let n = 0; n < 20; n++) expect(sample(unknown, n, n, 1, 0)).toBeNull();
});
