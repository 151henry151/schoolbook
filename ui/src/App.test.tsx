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
  vi.mocked(startMic).mockResolvedValue(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => ({ token: "boot" }) })),
  );
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.stubGlobal(
    "AudioContext",
    class {
      resume() {
        return Promise.resolve();
      }
      createBuffer() {
        return { getChannelData: () => new Float32Array(8) };
      }
      createBufferSource() {
        return {
          connect() {},
          start() {
            queueMicrotask(() => this.onended?.());
          },
          buffer: null,
          onended: null as (() => void) | null,
        };
      }
      get destination() {
        return {};
      }
    },
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("child and tutor lines stay on screen together", async () => {
  render(<App />);
  await vi.waitFor(() => expect(sockets.length).toBe(1));
  const socket = sockets[0];
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "hello_ok", voice: "realtime", learner_name: "Arum" }),
    } as MessageEvent);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Arum" }));
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({
        type: "transcript",
        role: "child",
        text: "Show me dinosaurs.",
      }),
    } as MessageEvent);
    socket.onmessage?.({
      data: JSON.stringify({
        type: "transcript",
        role: "tutor",
        text: "I will put on a dinosaur video.",
      }),
    } as MessageEvent);
  });
  expect(screen.getByText("Show me dinosaurs.")).toBeTruthy();
  expect(screen.getByText((_, node) => node?.textContent === "I will put on a dinosaur video.")).toBeTruthy();
});

test("listening and thinking use icons instead of words", async () => {
  render(<App />);
  await vi.waitFor(() => expect(sockets.length).toBe(1));
  const socket = sockets[0];
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "hello_ok", voice: "realtime", learner_name: "Arum" }),
    } as MessageEvent);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Arum" }));
  expect(await screen.findByRole("status", { name: "listening" })).toBeTruthy();
  expect(screen.getByRole("img", { name: "listening" }).className).toContain("status-ear");
  expect(screen.queryByText("Listening")).toBeNull();
  expect(screen.queryByText("I hear you")).toBeNull();
  expect(screen.queryByRole("button", { name: "Home" })).toBeNull();
  const listeningRow = document.querySelector(".talk-controls");
  const listeningParts = [...(listeningRow?.children ?? [])];
  expect(listeningParts[0]?.getAttribute("aria-label")).toBe("start talking");
  expect(listeningParts[1]?.getAttribute("aria-label")).toBe("listening");
  expect(listeningParts[2]?.getAttribute("aria-label")).toBe("stop");
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "state", name: "thinking" }),
    } as MessageEvent);
  });
  expect(await screen.findByRole("status", { name: "thinking" })).toBeTruthy();
  expect(screen.getByRole("img", { name: "thinking" }).className).toContain("status-brain");
  expect(screen.queryByText("Thinking")).toBeNull();
});

test("the child's line waits for the finished sentence the agent heard", async () => {
  render(<App />);
  await vi.waitFor(() => expect(sockets.length).toBe(1));
  const socket = sockets[0];
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "hello_ok", voice: "realtime", learner_name: "Arum" }),
    } as MessageEvent);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Arum" }));
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({
        type: "transcript",
        role: "child",
        text: "The deep",
        partial: true,
      }),
    } as MessageEvent);
  });
  expect(screen.queryByText("The deep")).toBeNull();
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({
        type: "transcript",
        role: "child",
        text: "How deep can a great white shark go?",
        partial: false,
      }),
    } as MessageEvent);
  });
  expect(screen.getByText("How deep can a great white shark go?")).toBeTruthy();
});

test("a blocked microphone is shown after the avatar tap", async () => {
  vi.mocked(startMic).mockRejectedValue(new Error("Permission denied"));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "friend" }));
  expect(await screen.findByRole("status", { name: "I cannot hear the microphone" })).toBeTruthy();
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
  fireEvent.click(screen.getByLabelText("pause or play"));
  await vi.waitFor(() => expect(listeners.length).toBe(1));
  expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: "video_ui", action: "pause" }));
  act(() => {
    listeners[0](new Int16Array(8), 20);
  });
  expect(socket.send.mock.calls.some((call) => String(call[0]).includes("audio_frame"))).toBe(true);
  socket.send.mockClear();
  fireEvent.click(screen.getByLabelText("pause or play"));
  await vi.waitFor(() => expect(listeners.length).toBe(0));
  expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: "video_ui", action: "resume" }));
  fireEvent.click(screen.getByRole("button", { name: "close video" }));
  await vi.waitFor(() => expect(listeners.length).toBe(1));
  expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: "video_ui", action: "done" }));
  act(() => {
    listeners[0](new Int16Array(8), 20);
  });
  expect(socket.send.mock.calls.some((call) => String(call[0]).includes("audio_frame"))).toBe(true);
});

test("a song plays audio without showing the music video", async () => {
  render(<App />);
  await vi.waitFor(() => expect(sockets.length).toBe(1));
  const socket = sockets[0];
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "hello_ok", voice: "realtime", learner_name: "Arum" }),
    } as MessageEvent);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Arum" }));
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({
        type: "video",
        action: "play",
        video_id: "songid11111",
        audio_only: true,
      }),
    } as MessageEvent);
  });
  expect(await screen.findByLabelText("song")).toBeTruthy();
  expect(screen.getByLabelText("song").className).toContain("audio-only");
});

test("a picture hides the talk words so the image is in focus", async () => {
  render(<App />);
  await vi.waitFor(() => expect(sockets.length).toBe(1));
  const socket = sockets[0];
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "hello_ok", voice: "realtime", learner_name: "Arum" }),
    } as MessageEvent);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Arum" }));
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({
        type: "transcript",
        role: "child",
        text: "How big is a pterodactyl?",
      }),
    } as MessageEvent);
    socket.onmessage?.({
      data: JSON.stringify({
        type: "transcript",
        role: "tutor",
        text: "About as wide as a house door.",
      }),
    } as MessageEvent);
    socket.onmessage?.({
      data: JSON.stringify({ type: "picture", image_id: "pterodactyl", loading: true }),
    } as MessageEvent);
  });
  expect(screen.queryByText("How big is a pterodactyl?")).toBeNull();
  expect(screen.queryByLabelText("what we said")).toBeNull();
  expect(screen.queryByText("Listening")).toBeNull();
  expect(await screen.findByRole("status", { name: "making a picture" })).toBeTruthy();
  expect(screen.getByLabelText("picture").className).toContain("above-controls");
  expect(screen.getByRole("button", { name: "start talking" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "stop" })).toBeTruthy();
});

test("a loading picture message shows a placeholder right away", async () => {
  render(<App />);
  await vi.waitFor(() => expect(sockets.length).toBe(1));
  const socket = sockets[0];
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "hello_ok", voice: "realtime", learner_name: "Arum" }),
    } as MessageEvent);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Arum" }));
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "picture", image_id: "shark-depth", loading: true }),
    } as MessageEvent);
  });
  expect(await screen.findByRole("status", { name: "making a picture" })).toBeTruthy();
});

test("a picture message shows the image and keeps the microphone on", async () => {
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
    socket.onmessage?.({
      data: JSON.stringify({ type: "picture", image_id: "dinosaur" }),
    } as MessageEvent);
  });
  expect((await screen.findByRole("img", { name: "dinosaur" })).getAttribute("src")).toBe(
    "/pictures/dinosaur",
  );
  expect(listeners.length).toBe(1);
  socket.send.mockClear();
  act(() => {
    listeners[0](new Int16Array(8), 20);
  });
  expect(socket.send.mock.calls.some((call) => String(call[0]).includes("audio_frame"))).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "close picture" }));
  expect(screen.queryByRole("img", { name: "dinosaur" })).toBeNull();
});

test("launching a game stops talk and shows a close button", async () => {
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
    socket.onmessage?.({
      data: JSON.stringify({
        type: "audio_chunk",
        turn_id: "live",
        seq: 0,
        pcm_b64: "AAAA",
        sample_rate: 24000,
      }),
    } as MessageEvent);
  });
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({
        type: "launch",
        app_id: "gcompris",
        argv: ["gcompris-qt", "--launch", "memory"],
      }),
    } as MessageEvent);
  });
  expect(await screen.findByRole("button", { name: "close game" })).toBeTruthy();
  await vi.waitFor(() => expect(listeners.length).toBe(0));
  fireEvent.click(screen.getByRole("button", { name: "close game" }));
  expect(screen.queryByRole("button", { name: "close game" })).toBeNull();
  expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: "app_ui", action: "done" }));
  await vi.waitFor(() => expect(listeners.length).toBe(1));
});

test("the microphone button stops talk and starts a fresh listen", async () => {
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
    socket.onmessage?.({
      data: JSON.stringify({ type: "state", name: "speaking" }),
    } as MessageEvent);
    socket.onmessage?.({
      data: JSON.stringify({
        type: "audio_chunk",
        turn_id: "live",
        pcm_b64: "AAA=",
        sample_rate: 24000,
      }),
    } as MessageEvent);
  });
  socket.send.mockClear();
  act(() => {
    listeners[0](new Int16Array(8), 20);
  });
  expect(socket.send.mock.calls.some((call) => String(call[0]).includes("audio_frame"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "start talking" }));
  expect(await screen.findByRole("status", { name: "listening" })).toBeTruthy();
  expect(
    socket.send.mock.calls.some((call) => {
      const body = JSON.parse(String(call[0])) as { type?: string };
      return body.type === "talk_start";
    }),
  ).toBe(true);
  socket.send.mockClear();
  act(() => {
    listeners[0](new Int16Array(8), 20);
  });
  expect(socket.send.mock.calls.some((call) => String(call[0]).includes("audio_frame"))).toBe(true);
});

test("the stop button pauses listening until the microphone starts it again", async () => {
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
  expect(screen.getByRole("button", { name: "stop" })).toBeTruthy();
  socket.send.mockClear();
  act(() => {
    listeners[0](new Int16Array(8), 20);
  });
  expect(socket.send.mock.calls.some((call) => String(call[0]).includes("audio_frame"))).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "stop" }));
  expect(screen.queryByText("Paused")).toBeNull();
  const paused = screen.getByRole("img", { name: "paused" });
  expect(paused.className).toContain("pause-mark");
  const controls = document.querySelector(".talk-controls");
  const parts = [...(controls?.children ?? [])];
  expect(parts[0]?.getAttribute("aria-label")).toBe("start talking");
  expect(parts[1]).toBe(paused);
  expect(parts[2]?.getAttribute("aria-label")).toBe("stop");
  await vi.waitFor(() => expect(listeners.length).toBe(0));
  socket.send.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "start talking" }));
  expect(await screen.findByRole("status", { name: "listening" })).toBeTruthy();
  await vi.waitFor(() => expect(listeners.length).toBe(1));
  act(() => {
    listeners[0](new Int16Array(8), 20);
  });
  expect(socket.send.mock.calls.some((call) => String(call[0]).includes("audio_frame"))).toBe(true);
});

test("the microphone button stays available over a paused video and hides while it plays", async () => {
  render(<App />);
  await vi.waitFor(() => expect(sockets.length).toBe(1));
  const socket = sockets[0];
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "hello_ok", voice: "realtime", learner_name: "Arum" }),
    } as MessageEvent);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Arum" }));
  expect(screen.getByRole("button", { name: "start talking" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "stop" })).toBeTruthy();
  expect(screen.queryByRole("img", { name: "paused" })).toBeNull();
  const idle = document.querySelector(".talk-controls");
  expect(idle?.className).toContain("centered");
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "video", action: "play", video_id: "abcdefghijk" }),
    } as MessageEvent);
  });
  expect(await screen.findByTitle("video")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "start talking" })).toBeNull();
  expect(screen.queryByRole("button", { name: "stop" })).toBeNull();
  fireEvent.click(screen.getByLabelText("pause or play"));
  expect(screen.getByRole("button", { name: "start talking" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "stop" })).toBeTruthy();
});

test("a picture over a paused video keeps the player so resume can continue", async () => {
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
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "video", action: "play", video_id: "abcdefghijk" }),
    } as MessageEvent);
  });
  expect(await screen.findByTitle("video")).toBeTruthy();
  fireEvent.click(screen.getByLabelText("pause or play"));
  await vi.waitFor(() => expect(listeners.length).toBe(1));
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "picture", image_id: "blue-whale-school-bus" }),
    } as MessageEvent);
  });
  expect(await screen.findByRole("img", { name: "blue-whale-school-bus" })).toBeTruthy();
  expect(screen.getByTitle("video")).toBeTruthy();
  expect(listeners.length).toBe(1);
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({ type: "video", action: "resume" }),
    } as MessageEvent);
  });
  await vi.waitFor(() => expect(screen.queryByRole("img", { name: "blue-whale-school-bus" })).toBeNull());
  expect(screen.getByTitle("video")).toBeTruthy();
  await vi.waitFor(() => expect(listeners.length).toBe(0));
});
