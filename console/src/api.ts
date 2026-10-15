// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export function apiUrl(path: string, page = window.location.href): string {
  return new URL(path.replace(/^\/+/, ""), new URL("./", page)).pathname;
}
export async function request(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), { ...init, credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(15000) });
  } catch {
    throw new ApiError(0, "Cannot reach Schoolbook. Check your connection and try again.");
  }
  if (!response.ok) {
    const message = response.status === 401 ? "Enter the parent password to unlock."
      : response.status === 429 ? "Too many attempts. Please wait before trying again."
      : [502, 503, 504].includes(response.status) ? "The Schoolbook laptop is offline. Try again when it is connected."
      : "Schoolbook could not complete that action. Please try again.";
    throw new ApiError(response.status, message);
  }
  return response.json();
}
export function jsonBody(value: unknown, method = "POST"): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(value) };
}
