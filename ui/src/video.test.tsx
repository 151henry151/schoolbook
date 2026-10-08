// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { fireEvent, render, screen } from "@testing-library/react";
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
  const target = { postMessage: vi.fn() };
  render(<VideoOverlay videoId="abcdefghijk" onClose={closed} player={target} />);
  fireEvent.click(screen.getByLabelText("pause or play"));
  expect(target.postMessage).toHaveBeenCalledWith(
    JSON.stringify({ event: "command", func: "pauseVideo", args: [] }),
    "https://www.youtube-nocookie.com",
  );
  fireEvent.click(screen.getByLabelText("pause or play"));
  expect(target.postMessage).toHaveBeenLastCalledWith(
    JSON.stringify({ event: "command", func: "playVideo", args: [] }),
    "https://www.youtube-nocookie.com",
  );
  fireEvent.click(screen.getByRole("button", { name: "close video" }));
  expect(closed).toHaveBeenCalledOnce();
});

test("playerCommand posts a YouTube iframe command", () => {
  const target = { postMessage: vi.fn() };
  playerCommand(target, "pauseVideo");
  expect(target.postMessage).toHaveBeenCalledWith(
    JSON.stringify({ event: "command", func: "pauseVideo", args: [] }),
    "https://www.youtube-nocookie.com",
  );
});
