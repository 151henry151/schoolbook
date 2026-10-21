// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { fireEvent, render, screen } from "@testing-library/react";
import { ParentUnlock } from "./unlock";

test("a correct password shows end session", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).endsWith("/unlock")) {
        const body = JSON.parse(String(init?.body)) as { action?: string };
        if (body.action === "end") {
          return { ok: true, json: async () => ({ ok: true, ended: true }) };
        }
        return { ok: true, json: async () => ({ ok: true, menu: ["console", "end"] }) };
      }
      return { ok: false, json: async () => ({ error: "bad" }) };
    }),
  );
  render(<ParentUnlock token="boot-token" />);
  fireEvent.change(screen.getByLabelText("parent password"), { target: { value: "parent-secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock" }));
  expect(await screen.findByRole("button", { name: "End session" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "End session" }));
  const fetchMock = vi.mocked(fetch);
  const endCall = fetchMock.mock.calls.find((call) => String(call[1]?.body).includes('"end"'));
  expect(endCall?.[1]?.headers).toMatchObject({ "x-schoolbook-token": "boot-token" });
});

test("the parent menu opens a Wi-Fi picker", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).endsWith("/unlock")) {
        return { ok: true, json: async () => ({ ok: true, menu: ["console", "end"] }) };
      }
      if (String(url).endsWith("/wifi") && !init?.method) {
        return {
          ok: true,
          json: async () => ({
            connected: false,
            ssid: null,
            online: false,
            networks: [{ ssid: "Grandpa", signal: 70, secured: true }],
          }),
        };
      }
      return { ok: false, json: async () => ({ error: "bad" }) };
    }),
  );
  render(<ParentUnlock token="boot-token" />);
  fireEvent.change(screen.getByLabelText("parent password"), { target: { value: "parent-secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock" }));
  fireEvent.click(await screen.findByRole("button", { name: "Wi-Fi" }));
  expect(await screen.findByRole("button", { name: "Grandpa" })).toBeTruthy();
});
