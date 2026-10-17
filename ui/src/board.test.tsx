// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { render, screen } from "@testing-library/react";
import { Board } from "./board";

test("renders big text and a capped row of dots", () => {
  render(
    <Board
      elements={[
        { type: "big_text", text: "shark" },
        { type: "dots", count: 3, emoji: "●" },
      ]}
    />,
  );
  expect(screen.getByText("shark")).toBeTruthy();
  expect(screen.getByText("●●●")).toBeTruthy();
});

test("a library picture is an image, not the word Picture", () => {
  render(<Board elements={[{ type: "image", image_id: "dinosaur" }]} />);
  const image = screen.getByRole("img", { name: "dinosaur" });
  expect(image.getAttribute("src")).toBe("/pictures/dinosaur");
  expect(screen.queryByText(/Picture:/)).toBeNull();
});

test("a broken board element does not crash the page", () => {
  render(
    <Board
      elements={[
        { type: "shapes", items: undefined as unknown as [] },
        { type: "big_text", text: "still here" },
      ]}
    />,
  );
  expect(screen.getByText("still here")).toBeTruthy();
});
