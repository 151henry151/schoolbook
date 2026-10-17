// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { act, fireEvent, render, screen } from "@testing-library/react";
import { playerCommand } from "./capture";
import { VideoOverlay } from "./video";

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

test("the overlay autoplays without written play pause or done labels", () => {
  const view = render(<VideoOverlay videoId="abcdefghijk" onClose={() => {}} />);
  const frame = screen.getByTitle("video");
  expect(frame.getAttribute("src")).toContain("youtube-nocookie.com");
  expect(frame.getAttribute("src")).toContain("autoplay=1");
  expect(screen.queryByRole("button", { name: "Play" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Done" })).toBeNull();
  expect(screen.getByRole("button", { name: "close video" })).toBeTruthy();
  view.unmount();
  expect(screen.queryByTitle("video")).toBeNull();
});

test("a tap pauses then resumes and the X closes the video", () => {
  const closed = vi.fn();
  const paused = vi.fn();
  const target = { postMessage: vi.fn() };
  render(
    <VideoOverlay videoId="abcdefghijk" onClose={closed} onPausedChange={paused} player={target} />,
  );
  fireEvent.click(screen.getByLabelText("pause or play"));
  expect(target.postMessage).toHaveBeenCalledWith(
    JSON.stringify({ event: "command", func: "pauseVideo", args: [] }),
    "https://www.youtube-nocookie.com",
  );
  expect(paused).toHaveBeenCalledWith(true);
  fireEvent.click(screen.getByLabelText("pause or play"));
  expect(target.postMessage).toHaveBeenLastCalledWith(
    JSON.stringify({ event: "command", func: "playVideo", args: [] }),
    "https://www.youtube-nocookie.com",
  );
  expect(paused).toHaveBeenLastCalledWith(false);
  fireEvent.click(screen.getByRole("button", { name: "close video" }));
  expect(closed).toHaveBeenCalledOnce();
});

test("a paused prop tells the player to pause or play", () => {
  const target = { postMessage: vi.fn() };
  const view = render(
    <VideoOverlay videoId="abcdefghijk" paused onClose={() => {}} player={target} />,
  );
  expect(target.postMessage).toHaveBeenCalledWith(
    JSON.stringify({ event: "command", func: "pauseVideo", args: [] }),
    "https://www.youtube-nocookie.com",
  );
  view.rerender(
    <VideoOverlay videoId="abcdefghijk" paused={false} onClose={() => {}} player={target} />,
  );
  expect(target.postMessage).toHaveBeenLastCalledWith(
    JSON.stringify({ event: "command", func: "playVideo", args: [] }),
    "https://www.youtube-nocookie.com",
  );
});

test("a playing video hides the cursor until the mouse moves", () => {
  vi.useFakeTimers();
  render(<VideoOverlay videoId="abcdefghijk" onClose={() => {}} />);
  const overlay = screen.getByLabelText("video");
  expect(overlay.className).toContain("cursor-idle");
  fireEvent.mouseMove(overlay);
  expect(overlay.className).not.toContain("cursor-idle");
  act(() => {
    vi.advanceTimersByTime(2500);
  });
  expect(overlay.className).toContain("cursor-idle");
  vi.useRealTimers();
});

test("audio-only playback uses a local song stream", () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  render(<VideoOverlay videoId="songid11111" audioOnly onClose={() => {}} />);
  const overlay = screen.getByLabelText("song");
  expect(overlay.className).toContain("audio-only");
  expect(screen.queryByTitle("video")).toBeNull();
  const audio = document.querySelector("audio");
  expect(audio).toBeTruthy();
  expect(audio?.getAttribute("src")).toBe("/songs/songid11111");
  expect(audio?.hasAttribute("autoplay")).toBe(true);
  expect(screen.getByLabelText("pause or play").className).toContain("song-cover");
  play.mockRestore();
});

test("a tap pauses then resumes a song", () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  const paused = vi.fn();
  render(<VideoOverlay videoId="songid11111" audioOnly onClose={() => {}} onPausedChange={paused} />);
  fireEvent.click(screen.getByLabelText("pause or play"));
  expect(pause).toHaveBeenCalled();
  expect(paused).toHaveBeenCalledWith(true);
  fireEvent.click(screen.getByLabelText("pause or play"));
  expect(play).toHaveBeenCalled();
  expect(paused).toHaveBeenLastCalledWith(false);
  play.mockRestore();
  pause.mockRestore();
});

test("a paused video keeps the cursor visible", () => {
  render(<VideoOverlay videoId="abcdefghijk" paused onClose={() => {}} />);
  expect(screen.getByLabelText("video").className).not.toContain("cursor-idle");
});

test("the overlay closes when the youtube player ends", () => {
  const closed = vi.fn();
  render(<VideoOverlay videoId="abcdefghijk" onClose={closed} />);
  act(() => {
    window.dispatchEvent(
      new MessageEvent("message", {
        origin: "https://www.youtube-nocookie.com",
        data: JSON.stringify({ event: "infoDelivery", info: { playerState: 0 } }),
      }),
    );
  });
  expect(closed).toHaveBeenCalledOnce();
});

test("a playing or paused youtube state does not close the overlay", () => {
  const closed = vi.fn();
  render(<VideoOverlay videoId="abcdefghijk" onClose={closed} />);
  act(() => {
    window.dispatchEvent(
      new MessageEvent("message", {
        origin: "https://www.youtube-nocookie.com",
        data: JSON.stringify({ event: "infoDelivery", info: { playerState: 1 } }),
      }),
    );
    window.dispatchEvent(
      new MessageEvent("message", {
        origin: "https://www.youtube-nocookie.com",
        data: { event: "onStateChange", info: 2 },
      }),
    );
  });
  expect(closed).not.toHaveBeenCalled();
});

test("playerCommand posts a YouTube iframe command", () => {
  const target = { postMessage: vi.fn() };
  playerCommand(target, "pauseVideo");
  expect(target.postMessage).toHaveBeenCalledWith(
    JSON.stringify({ event: "command", func: "pauseVideo", args: [] }),
    "https://www.youtube-nocookie.com",
  );
});

test("the song has a visible keyboard-accessible pause and play button", () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  const changed = vi.fn();
  const started = vi.fn();
  render(<VideoOverlay videoId="songid11111" audioOnly onClose={() => {}} onPausedChange={changed} onPlaying={started} />);
  fireEvent.playing(document.querySelector("audio")!);
  expect(started).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Pause music" }));
  expect(pause).toHaveBeenCalled();
  expect(changed).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole("button", { name: "Play music" }));
  expect(play).toHaveBeenCalled();
  expect(changed).toHaveBeenLastCalledWith(false);
  expect(screen.getByLabelText("song").className).not.toContain("cursor-idle");
  play.mockRestore(); pause.mockRestore();
});

test('reports halfway watched from real player progress messages only once', () => {
  const watched = vi.fn();
  const clock = vi.spyOn(performance, 'now');
  render(<VideoOverlay videoId="abcdefghijk" onClose={() => {}} onWatched={watched} />);
  for (let n = 0; n <= 60; n++) {
    clock.mockReturnValue(n * 1000);
    act(() => window.dispatchEvent(new MessageEvent('message', {
      origin: 'https://www.youtube-nocookie.com',
      data: JSON.stringify({ event: 'infoDelivery', info: { currentTime: n, duration: 100, playerState: 1 } }),
    })));
  }
  expect(watched).toHaveBeenCalledOnce();
  expect(watched).toHaveBeenCalledWith({ watched_s: 50, duration_s: 100 });
  clock.mockRestore();
});

test("video volume applies on readiness and changes without pausing or restarting playback", () => {
  localStorage.setItem("schoolbook.media-volume", "40");
  const target = { postMessage: vi.fn() };
  const paused = vi.fn();
  render(<VideoOverlay videoId="abcdefghijk" onClose={() => {}} onPausedChange={paused} player={target} />);
  expect((screen.getByRole("slider", { name: "Playback volume" }) as HTMLInputElement).value).toBe("40");
  // A change before the embedded player is ready must survive its onReady event.
  fireEvent.click(screen.getByRole("button", { name: "Volume down" }));
  target.postMessage.mockClear();
  act(() => window.dispatchEvent(new MessageEvent("message", {
    origin: "https://www.youtube-nocookie.com", data: JSON.stringify({ event: "onReady" }),
  })));
  expect(JSON.parse(target.postMessage.mock.calls[0][0])).toEqual({ event: "command", func: "setVolume", args: [30] });
  target.postMessage.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "Volume up" }));
  expect(target.postMessage.mock.calls.map(([data]) => JSON.parse(data).func)).toEqual(["setVolume", "unMute"]);
  expect(JSON.parse(target.postMessage.mock.calls[0][0]).args).toEqual([40]);
  expect(paused).not.toHaveBeenCalled();
});

test("song volume reaches silence, stays bounded, and carries over to the next player", () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  const changed = vi.fn();
  const view = render(<VideoOverlay videoId="songid11111" audioOnly onClose={() => {}} onPausedChange={changed} />);
  const audio = document.querySelector("audio")!;
  play.mockClear();
  const slider = screen.getByRole("slider", { name: "Playback volume" });
  fireEvent.change(slider, { target: { value: "5" } });
  expect(audio.volume).toBe(0.05);
  fireEvent.click(screen.getByRole("button", { name: "Volume down" }));
  expect(audio.volume).toBe(0);
  expect(slider.getAttribute("aria-valuetext")).toBe("Muted");
  expect((screen.getByRole("button", { name: "Volume down" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(slider, { target: { value: "95" } });
  fireEvent.click(screen.getByRole("button", { name: "Volume up" }));
  expect(audio.volume).toBe(1);
  expect((screen.getByRole("button", { name: "Volume up" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(slider, { target: { value: "35" } });
  expect(play).not.toHaveBeenCalled();
  expect(pause).not.toHaveBeenCalled();
  expect(changed).not.toHaveBeenCalled();
  view.unmount();
  const target = { postMessage: vi.fn() };
  render(<VideoOverlay videoId="anothervid1" onClose={() => {}} player={target} />);
  expect((screen.getByRole("slider") as HTMLInputElement).value).toBe("35");
  expect(target.postMessage).toHaveBeenCalledWith(
    JSON.stringify({ event: "command", func: "setVolume", args: [35] }), "https://www.youtube-nocookie.com",
  );
  play.mockRestore(); pause.mockRestore();
});

test.each(["not a volume", "NaN", "-1", "101", ""])("invalid saved volume %s does not break playback", (saved) => {
  localStorage.setItem("schoolbook.media-volume", saved);
  render(<VideoOverlay videoId="abcdefghijk" onClose={() => {}} />);
  expect((screen.getByRole("slider") as HTMLInputElement).value).toBe("100");
});

test("volume still works when browser storage is blocked", () => {
  const read = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  render(<VideoOverlay videoId="abcdefghijk" onClose={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Volume down" }));
  expect((screen.getByRole("slider") as HTMLInputElement).value).toBe("90");
  read.mockRestore(); write.mockRestore();
});
