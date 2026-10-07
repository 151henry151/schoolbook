// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { fireEvent, render, screen } from "@testing-library/react";
import { VideoOverlay } from "./video";

test("the overlay covers the player and Done destroys it", () => {
  const done = vi.fn();
  const view = render(<VideoOverlay videoId="abcdefghijk" onDone={done} />);
  const frame = screen.getByTitle("video");
  expect(frame.getAttribute("src")).toContain("youtube-nocookie.com");
  fireEvent.click(screen.getByRole("button", { name: "Done" }));
  expect(done).toHaveBeenCalledOnce();
  view.unmount();
  expect(screen.queryByTitle("video")).toBeNull();
});
