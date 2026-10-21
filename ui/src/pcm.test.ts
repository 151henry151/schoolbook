// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { createVad, downsample, encodePcm16, floatToPcm16, rms16, voiced } from "./pcm";

test("loud samples count as voice and quiet samples do not", () => {
  const loud = new Int16Array([1200, -1100, 1300]);
  const quiet = new Int16Array([20, -10, 0]);
  const room = new Int16Array([180, -160, 200]);
  expect(voiced(loud)).toBe(true);
  expect(voiced(room)).toBe(false);
  expect(voiced(quiet)).toBe(false);
});

test("vad opens on speech energy and stays closed on room hiss", () => {
  const vad = createVad();
  const hiss = new Int16Array(160).fill(180);
  const speech = new Int16Array(160).fill(1200);
  expect(rms16(hiss)).toBeLessThan(400);
  expect(vad(hiss)).toBe(false);
  expect(vad(speech)).toBe(true);
  expect(vad(new Int16Array(160).fill(300))).toBe(true);
  expect(vad(new Int16Array(160).fill(20))).toBe(false);
});

test("float samples become little-endian pcm16 and downsample 48k to 16k", () => {
  const floats = new Float32Array([1, 0, -1]);
  const pcm = floatToPcm16(floats);
  expect(pcm[0]).toBe(32767);
  expect(pcm[2]).toBe(-32768);
  const encoded = encodePcm16(pcm);
  expect(atob(encoded).length).toBe(6);
  const high = new Float32Array(9).map((_, index) => (index % 3 === 0 ? 0.5 : 0));
  const down = downsample(high, 48000, 16000);
  expect(down.length).toBe(3);
});
