// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { render, screen } from "@testing-library/react";
import { TalkLines, nextTalkPair, speakerInitial, spokenWordIndex } from "./talkLines";

test("a tutor reply keeps the child's words", () => {
  const afterChild = nextTalkPair({ child: "", tutor: "" }, "child", "Show me dinosaurs.");
  const afterTutor = nextTalkPair(afterChild, "tutor", "I will put on a dinosaur video.");
  assertPair(afterTutor, "Show me dinosaurs.", "I will put on a dinosaur video.");
  const nextChild = nextTalkPair(afterTutor, "child", "Another one?");
  assertPair(nextChild, "Another one?", "");
});

test("spokenWordIndex follows elapsed playback", () => {
  expect(spokenWordIndex("one two three", 0, 3000)).toBe(0);
  expect(spokenWordIndex("one two three", 1500, 3000)).toBe(1);
  expect(spokenWordIndex("one two three", 2900, 3000)).toBe(2);
});

test("the spoken tutor word is marked for read-along", () => {
  render(
    <TalkLines
      name="Arum"
      child="Hi"
      tutor="I will put it on."
      spokenIndex={2}
    />,
  );
  expect(screen.getByText("put").className).toContain("spoken-now");
});

test("hidden talk lines take the words off the screen", () => {
  render(
    <TalkLines
      name="Arum"
      child="How big is a pterodactyl?"
      tutor="About as wide as a house door."
      hidden
    />,
  );
  expect(screen.queryByLabelText("what we said")).toBeNull();
  expect(screen.queryByText("How big is a pterodactyl?")).toBeNull();
});

test("talk lines show both speakers with initials", () => {
  render(
    <TalkLines name="Arum" child="Show me dinosaurs." tutor="I will put on a dinosaur video." />,
  );
  expect(screen.getByText("Show me dinosaurs.")).toBeTruthy();
  expect(screen.getByText((_, node) => node?.textContent === "I will put on a dinosaur video.")).toBeTruthy();
  expect(speakerInitial("Arum")).toBe("A");
  const icons = document.querySelectorAll(".talk-icon");
  expect(icons[0]?.textContent).toBe("A");
  expect(icons[1]?.textContent).toBe("S");
});

function assertPair(pair: { child: string; tutor: string }, child: string, tutor: string) {
  expect(pair.child).toBe(child);
  expect(pair.tutor).toBe(tutor);
}
