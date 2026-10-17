// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { fireEvent, render, screen } from "@testing-library/react";
import { App } from "./App";

test("a parent sees an open flag after unlocking", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).endsWith("/api/learners")) return { ok: true, json: async () => ({ active_learner_id: "kid", learners: [{id: "kid", first_name: "Arum"}, {id: "hannah", first_name: "Hannah"}] }) };
      if (String(url).endsWith("/api/login")) {
        return { ok: true, json: async () => ({ ok: true }) };
      }
      if (String(url).includes("/api/today")) {
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
    if (String(url).endsWith("/api/learners")) return { ok: true, json: async () => ({ active_learner_id: "kid", learners: [{id: "kid", first_name: "Arum"}, {id: "hannah", first_name: "Hannah"}] }) };
    if (init?.method === "POST") return { ok: false, status: 503 };
    if (String(url).includes("/api/today")) return { ok: true, json: async () => ({ in_session: true, screen: "home", minutes: 2, open_flags: [], latest_summary: "Learning.", model_calls: 1, spend_alert_cents: 0 }) };
    if (String(url).includes("/api/library/videos")) return { ok: true, json: async () => [{id: "song1", title: "A song", verdict: "approved", reasons: ""}] };
    return { ok: false, status: 404 };
  }));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", {name: "Library"}));
  fireEvent.click(await screen.findByRole("button", {name: "Block"}));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "The Schoolbook laptop is offline. Try again when it is connected.");
  expect(screen.queryByLabelText("parent password")).toBeNull();
  expect(screen.queryByText("Saved.")).toBeNull();
});

test("viewing Hannah scopes reads and edits without switching the child", async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith("/api/learners")) return {ok: true, json: async () => ({active_learner_id: "arum", learners: [{id: "arum", first_name: "Arum"}, {id: "hannah", first_name: "Hannah"}]})};
    if (String(url).includes("/api/today")) return {ok: true, json: async () => ({open_flags: [], minutes: 0, latest_summary: String(url).includes("hannah") ? "Hannah learned letters." : "Arum learned numbers."})};
    if (String(url).includes("/api/learner")) return {ok: true, json: async () => ({first_name: "Hannah"})};
    return {ok: true, json: async () => ({})};
  });
  vi.stubGlobal("fetch", fetcher);
  render(<App />);
  expect(await screen.findByText("Arum learned numbers.")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Viewing learner"), {target: {value: "hannah"}});
  expect(await screen.findByText("Hannah learned letters.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", {name: "Learner"}));
  expect(await screen.findByLabelText("child name")).toHaveProperty("value", "Hannah");
  fireEvent.click(screen.getByRole("button", {name: "Save"}));
  await vi.waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => String(url).endsWith("api/learner?learner_id=hannah") && init?.method === "PATCH")).toBe(true));
  expect(fetcher.mock.calls.some(([url]) => String(url).includes("select_learner"))).toBe(false);
});
