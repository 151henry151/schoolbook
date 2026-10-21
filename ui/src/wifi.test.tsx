// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { fireEvent, render, screen } from "@testing-library/react";
import { WifiSetup } from "./wifi";

test("lists nearby networks and joins the one that needs a password", async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith("/wifi") && !init?.method) {
      return {
        ok: true,
        json: async () => ({
          connected: false,
          ssid: null,
          online: false,
          networks: [
            { ssid: "Grandpa", signal: 70, secured: true },
            { ssid: "Cafe", signal: 20, secured: false },
          ],
        }),
      };
    }
    if (String(url).endsWith("/wifi/connect")) {
      const body = JSON.parse(String(init?.body)) as { ssid: string; password: string };
      expect(body).toEqual({ ssid: "Grandpa", password: "house-key" });
      return { ok: true, json: async () => ({ ok: true, connected: true, ssid: "Grandpa", online: true, networks: [] }) };
    }
    return { ok: false, json: async () => ({ error: "bad" }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<WifiSetup token="boot-token" />);
  fireEvent.click(await screen.findByRole("button", { name: "Grandpa" }));
  fireEvent.change(screen.getByLabelText("Wi-Fi password"), { target: { value: "house-key" } });
  fireEvent.click(screen.getByRole("button", { name: "Join" }));
  expect(await screen.findByText("Connected to Grandpa")).toBeTruthy();
  const connectCall = fetchMock.mock.calls.find((call) => String(call[0]).endsWith("/wifi/connect"));
  expect(connectCall?.[1]?.headers).toMatchObject({ "x-schoolbook-token": "boot-token" });
});
