// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { fireEvent, render, screen } from "@testing-library/react";
import { PictureOverlay } from "./picture";

test("the overlay shows the generated picture and an X to close", () => {
  const closed = vi.fn();
  render(<PictureOverlay imageId="dinosaur" onClose={closed} />);
  const image = screen.getByRole("img", { name: "dinosaur" });
  expect(image.getAttribute("src")).toBe("/pictures/dinosaur");
  fireEvent.click(screen.getByRole("button", { name: "close picture" }));
  expect(closed).toHaveBeenCalledOnce();
});
