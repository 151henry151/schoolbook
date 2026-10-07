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
