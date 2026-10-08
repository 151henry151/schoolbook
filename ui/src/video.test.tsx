// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { act, fireEvent, render, screen } from "@testing-library/react";
import { playerCommand } from "./capture";
import { VideoOverlay } from "./video";

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

test("playerCommand posts a YouTube iframe command", () => {
  const target = { postMessage: vi.fn() };
  playerCommand(target, "pauseVideo");
  expect(target.postMessage).toHaveBeenCalledWith(
    JSON.stringify({ event: "command", func: "pauseVideo", args: [] }),
    "https://www.youtube-nocookie.com",
  );
});
