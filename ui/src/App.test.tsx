// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { act, fireEvent, render, screen } from "@testing-library/react";
import { App } from "./App";
import { startMic } from "./mic";

vi.mock("./mic", () => ({
  startMic: vi.fn(),
  createCaptureContext: vi.fn(() => ({ resume: vi.fn(async () => {}) })),
}));

const sockets: FakeSocket[] = [];

class FakeSocket {
  static OPEN = 1;
  readyState = 1;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onopen: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor() {
    sockets.push(this);
    queueMicrotask(() => this.onopen?.());
  }
}

beforeEach(() => {
  sockets.length = 0;
  vi.mocked(startMic).mockReset();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => ({ token: "boot" }) })),
  );
  vi.stubGlobal("WebSocket", FakeSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("a blocked microphone is shown after the avatar tap", async () => {
  vi.mocked(startMic).mockRejectedValue(new Error("Permission denied"));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "friend" }));
  expect(await screen.findByText("I cannot hear the microphone")).toBeTruthy();
});

test("playing a video stops mic frames until the child closes it", async () => {
  const listeners: Array<(pcm: Int16Array, dtMs: number) => void> = [];
  vi.mocked(startMic).mockImplementation(async (onFrame) => {
    listeners.push(onFrame);
    return () => {
      const index = listeners.indexOf(onFrame);
      if (index >= 0) listeners.splice(index, 1);
    };
  });
  render(<App />);
  await vi.waitFor(() => expect(sockets.length).toBe(1));
  const socket = sockets[0];
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "hello_ok", voice: "realtime", learner_name: "Arum" }),
    } as MessageEvent);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Arum" }));
  await vi.waitFor(() => expect(listeners.length).toBe(1));
  act(() => {
    listeners[0](new Int16Array(8), 20);
  });
  expect(socket.send.mock.calls.some((call) => String(call[0]).includes("audio_frame"))).toBe(true);
  socket.send.mockClear();
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "video", action: "play", video_id: "abcdefghijk" }),
    } as MessageEvent);
  });
  expect(await screen.findByTitle("video")).toBeTruthy();
  await vi.waitFor(() => expect(listeners.length).toBe(0));
  fireEvent.click(screen.getByRole("button", { name: "close video" }));
  await vi.waitFor(() => expect(listeners.length).toBe(1));
  expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: "video_ui", action: "done" }));
  act(() => {
    listeners[0](new Int16Array(8), 20);
  });
  expect(socket.send.mock.calls.some((call) => String(call[0]).includes("audio_frame"))).toBe(true);
});
