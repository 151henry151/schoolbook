// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { render, screen } from "@testing-library/react";
import { TalkStatus } from "./talkStatus";

test("listening shows an ear and no words", () => {
  render(<TalkStatus kind="listening" />);
  expect(screen.getByRole("status", { name: "listening" })).toBeTruthy();
  expect(screen.getByRole("img", { name: "listening" }).className).toContain("status-ear");
  expect(screen.queryByText("Listening")).toBeNull();
  expect(screen.queryByText("I hear you")).toBeNull();
});

test("thinking shows a brain and no words", () => {
  render(<TalkStatus kind="thinking" />);
  expect(screen.getByRole("status", { name: "thinking" })).toBeTruthy();
  expect(screen.getByRole("img", { name: "thinking" }).className).toContain("status-brain");
  expect(screen.queryByText("Thinking")).toBeNull();
  expect(document.querySelectorAll(".brain-lobe").length).toBeGreaterThanOrEqual(2);
});
