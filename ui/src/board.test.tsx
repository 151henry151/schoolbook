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
