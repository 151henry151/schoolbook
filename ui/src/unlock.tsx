// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useState, type FormEvent } from "react";

export function ParentUnlock({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState("");

  async function unlock(event: FormEvent) {
    event.preventDefault();
    const response = await fetch("/unlock", {
      method: "POST",
      headers: { "content-type": "application/json", "x-schoolbook-token": token },
      body: JSON.stringify({ password }),
    });
    if (!response.ok) {
      setError("invalid password");
      return;
    }
    setMenu(true);
  }

  async function endSession() {
    await fetch("/unlock", {
      method: "POST",
      headers: { "content-type": "application/json", "x-schoolbook-token": token },
      body: JSON.stringify({ password, action: "end" }),
    });
  }

  if (menu) {
    return (
      <nav className="unlock" aria-label="parent menu">
        <button type="button" onClick={() => void endSession()}>
          End session
        </button>
      </nav>
    );
  }

  return (
    <form className="unlock" aria-label="parent unlock" onSubmit={(event) => void unlock(event)}>
      <input
        aria-label="parent password"
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
      />
      <button type="submit">Unlock</button>
      {error ? <p role="alert">{error}</p> : null}
    </form>
  );
}
