// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors
import { apiUrl, request } from "./api";

afterEach(() => vi.unstubAllGlobals());
test("API calls stay under the console prefix", () => {
  expect(apiUrl("/api/today", "https://romptele.com/schoolbook/")).toBe("/schoolbook/api/today");
  expect(apiUrl("api/memory?learner_id=hannah", "https://romptele.com/schoolbook/")).toBe("/schoolbook/api/memory?learner_id=hannah");
  expect(apiUrl("api/login", "http://localhost:8766/")).toBe("/api/login");
});
test("offline laptop and expired login are distinct failures", async () => {
  const fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 502 }).mockResolvedValueOnce({ ok: false, status: 401 });
  vi.stubGlobal("fetch", fetch);
  await expect(request("api/today")).rejects.toThrow("laptop is offline");
  await expect(request("api/today")).rejects.toMatchObject({ status: 401 });
  expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: "same-origin", cache: "no-store" });
});
