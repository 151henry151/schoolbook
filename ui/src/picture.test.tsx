// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { fireEvent, render, screen } from "@testing-library/react";
import { PictureOverlay } from "./picture";

test("a loading overlay shows a placeholder while the picture is made", () => {
  render(<PictureOverlay imageId="shark" loading onClose={() => {}} />);
  expect(screen.getByRole("status", { name: "making a picture" })).toBeTruthy();
  expect(screen.queryByRole("img", { name: "shark" })).toBeNull();
});

test("the overlay shows the generated picture and an X to close", () => {
  const closed = vi.fn();
  render(<PictureOverlay imageId="dinosaur" onClose={closed} />);
  const image = screen.getByRole("img", { name: "dinosaur" });
  expect(image.getAttribute("src")).toBe("/pictures/dinosaur");
  fireEvent.click(screen.getByRole("button", { name: "close picture" }));
  expect(closed).toHaveBeenCalledOnce();
});

test("the picture sits in a frame that leaves room for the talk buttons", () => {
  render(<PictureOverlay imageId="pterodactyl" onClose={() => {}} />);
  const overlay = screen.getByLabelText("picture");
  expect(overlay.className).toContain("above-controls");
  const image = screen.getByRole("img", { name: "pterodactyl" });
  expect(image.closest(".picture-frame")).toBeTruthy();
  expect(image.className).toContain("picture-fit");
});
