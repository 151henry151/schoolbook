// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { armed, stepHandsFree } from "./handsfree";

test("voice starts a turn, silence of 1.5s ends it, and speech does not barge in", () => {
  let ids = 0;
  const nextId = () => `t${++ids}`;
  const start = stepHandsFree(armed(), { voiced: true, dtMs: 40, speaking: false }, nextId);
  expect(start.event).toEqual({ type: "start", turnId: "t1" });
  let state = start.state;
  state = stepHandsFree(state, { voiced: true, dtMs: 300, speaking: false }, nextId).state;
  const ended = stepHandsFree(state, { voiced: false, dtMs: 1500, speaking: false }, nextId);
  expect(ended.event).toEqual({ type: "end", turnId: "t1" });
  const waiting = ended.state;
  const barge = stepHandsFree(waiting, { voiced: true, dtMs: 40, speaking: true }, nextId);
  expect(barge.event).toBeNull();
  expect(barge.state.phase).toBe("waiting");
});

test("a click of noise does not end a turn", () => {
  const start = stepHandsFree(armed(), { voiced: true, dtMs: 40, speaking: false }, () => "t1");
  const ended = stepHandsFree(start.state, { voiced: false, dtMs: 1500, speaking: false }, () => "t1");
  expect(ended.event?.type).not.toBe("end");
});

test("room noise after a pause does not start a new turn while thinking", () => {
  const nextId = () => "t2";
  const start = stepHandsFree(armed(), { voiced: true, dtMs: 300, speaking: false }, () => "t1");
  const ended = stepHandsFree(start.state, { voiced: false, dtMs: 1500, speaking: false }, nextId);
  expect(ended.event?.type).toBe("end");
  const leftover = stepHandsFree(ended.state, { voiced: true, dtMs: 40, speaking: false }, nextId);
  expect(leftover.event).toBeNull();
  expect(leftover.state.phase).toBe("waiting");
});

test("short noise during a pause still ends the turn", () => {
  let state = stepHandsFree(armed(), { voiced: true, dtMs: 300, speaking: false }, () => "t1").state;
  state = stepHandsFree(state, { voiced: false, dtMs: 600, speaking: false }, () => "t1").state;
  state = stepHandsFree(state, { voiced: true, dtMs: 40, speaking: false }, () => "t1").state;
  const ended = stepHandsFree(state, { voiced: false, dtMs: 1000, speaking: false }, () => "t1");
  expect(ended.event).toEqual({ type: "end", turnId: "t1" });
});

test("a long turn ends even if the mic never goes quiet", () => {
  let state = stepHandsFree(armed(), { voiced: true, dtMs: 300, speaking: false }, () => "t1").state;
  const ended = stepHandsFree(state, { voiced: true, dtMs: 8000, speaking: false }, () => "t1");
  expect(ended.event).toEqual({ type: "end", turnId: "t1" });
});
