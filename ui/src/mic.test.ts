// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { pickCaptureDeviceId, startMic } from "./mic";

test("capture prefers a real microphone over a speaker monitor", () => {
  expect(
    pickCaptureDeviceId([
      { kind: "audioinput", deviceId: "mon", label: "Monitor of Built-in Audio Analog Stereo" },
      { kind: "audioinput", deviceId: "mic", label: "Built-in Audio Analog Stereo" },
      { kind: "audiooutput", deviceId: "spk", label: "Speakers" },
    ]),
  ).toBe("mic");
});

function fakeContext(state: AudioContextState = "suspended") {
  const context = {
    state,
    sampleRate: 48000,
    destination: {},
    resume: vi.fn(async () => {
      context.state = "running";
    }),
    close: vi.fn(async () => {}),
    audioWorklet: { addModule: vi.fn(async () => {}) },
    createMediaStreamSource: vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() })),
    createGain: vi.fn(() => ({ gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() })),
    createScriptProcessor: vi.fn(() => ({
      onaudioprocess: null,
      connect: vi.fn(),
      disconnect: vi.fn(),
    })),
  };
  return context as unknown as AudioContext & { resume: ReturnType<typeof vi.fn> };
}

beforeEach(() => {
  vi.stubGlobal(
    "navigator",
    {
      mediaDevices: {
        enumerateDevices: vi.fn(async () => [
          { kind: "audioinput", deviceId: "mon", label: "Monitor of Built-in Audio Analog Stereo" },
          { kind: "audioinput", deviceId: "mic", label: "Microphone" },
        ]),
        getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn(), label: "Microphone" }] })),
      },
    },
  );
  vi.stubGlobal(
    "AudioWorkletNode",
    class {
      port = { onmessage: null };
      connect = vi.fn();
      disconnect = vi.fn();
    },
  );
  vi.stubGlobal("URL", {
    createObjectURL: () => "blob:mic",
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("a suspended capture context is resumed before frames are wired", async () => {
  const context = fakeContext("suspended");
  await startMic(() => {}, context);
  expect(context.resume).toHaveBeenCalled();
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
    audio: expect.objectContaining({
      deviceId: { ideal: "mic" },
      echoCancellation: false,
      noiseSuppression: false,
    }),
  });
});

test("a blocked microphone rejects so the UI can say so", async () => {
  vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValueOnce(new DOMException("denied", "NotAllowedError"));
  await expect(startMic(() => {}, fakeContext("running"))).rejects.toThrow(/denied|NotAllowedError|microphone/i);
});

test("worklet failure still starts capture through the script processor", async () => {
  const context = fakeContext("running");
  (context.audioWorklet.addModule as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("no worklet"));
  const stop = await startMic(() => {}, context);
  expect(context.createScriptProcessor).toHaveBeenCalled();
  stop();
});
