// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { fireEvent, render, screen } from "@testing-library/react";
import { App } from "./App";

test("a parent sees an open flag after unlocking", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).endsWith("/api/login")) {
        return { ok: true, json: async () => ({ ok: true }) };
      }
      if (String(url).endsWith("/api/today")) {
        return {
          ok: true,
          json: async () => ({
            in_session: true,
            paused: false,
            screen: "home",
            minutes: 4,
            open_flags: [{ id: "f1", reason: "distress", severity: "high", excerpt: "I am scared" }],
            latest_summary: "Counted sharks.",
            model_calls: 2,
            spend_alert_cents: 0,
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    }),
  );
  render(<App />);
  fireEvent.change(screen.getByLabelText("parent password"), { target: { value: "secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock" }));
  expect(await screen.findByText(/distress/)).toBeTruthy();
  expect(screen.getByText(/I am scared/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Library" })).toBeTruthy();
});

test("restores a signed-in parent and reports a failed action without logging out", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") return { ok: false, status: 503 };
    if (String(url).endsWith("/api/today")) return { ok: true, json: async () => ({ in_session: true, screen: "home", minutes: 2, open_flags: [], latest_summary: "Learning.", model_calls: 1, spend_alert_cents: 0 }) };
    if (String(url).endsWith("/api/library/videos")) return { ok: true, json: async () => [{id: "song1", title: "A song", verdict: "approved", reasons: ""}] };
    return { ok: false, status: 404 };
  }));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", {name: "Library"}));
  fireEvent.click(await screen.findByRole("button", {name: "Block"}));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "The Schoolbook laptop is offline. Try again when it is connected.");
  expect(screen.queryByLabelText("parent password")).toBeNull();
  expect(screen.queryByText("Saved.")).toBeNull();
});
