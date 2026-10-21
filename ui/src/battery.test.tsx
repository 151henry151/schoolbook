// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { act, cleanup, render, screen } from "@testing-library/react";
import { BatteryIndicator } from "./battery";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("refreshes battery level and charging state, then stops polling on unmount", async () => {
  vi.useFakeTimers();
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ percent: 82, charging: true }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ percent: 19, charging: false }) });
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<BatteryIndicator />);
  await act(async () => {});
  expect(screen.getByRole("img", { name: "Battery 82%, charging" })).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
  expect(screen.getByRole("img", { name: "Battery 19%, low" }).className).toContain("is-low");
  view.unmount();
  await vi.advanceTimersByTimeAsync(60_000);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("shows an empty battery but hides an unavailable or failed reading", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ percent: 0, charging: false }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ percent: null, charging: false }) })
    .mockRejectedValueOnce(new Error("offline")));
  render(<BatteryIndicator />);
  await act(async () => {});
  expect(screen.getByRole("img", { name: "Battery 0%, low" })).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
  expect(screen.queryByRole("img")).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
  expect(screen.queryByRole("img")).toBeNull();
});
