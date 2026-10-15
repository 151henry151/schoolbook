// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useState, type FormEvent } from "react";

type Network = { ssid: string; signal: number; secured: boolean };

type Status = {
  connected: boolean;
  ssid: string | null;
  online: boolean;
  networks: Network[];
  error?: string;
};

export function WifiSetup({ token }: { token: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [picked, setPicked] = useState<Network | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [joining, setJoining] = useState(false);

  async function load() {
    const response = await fetch("/wifi");
    const body = (await response.json()) as Status;
    setStatus(body);
    if (!response.ok) setError(body.error || "Wi-Fi is not ready");
  }

  useEffect(() => {
    void load();
  }, []);

  async function join(event: FormEvent) {
    event.preventDefault();
    if (!picked) return;
    setJoining(true);
    setError("");
    const response = await fetch("/wifi/connect", {
      method: "POST",
      headers: { "content-type": "application/json", "x-schoolbook-token": token },
      body: JSON.stringify({ ssid: picked.ssid, password }),
    });
    const body = (await response.json()) as Status & { ok?: boolean };
    setJoining(false);
    if (!response.ok) {
      setError(body.error || "could not join");
      return;
    }
    setStatus(body);
    setPicked(null);
    setPassword("");
  }

  const connected = status?.ssid && status.connected ? `Connected to ${status.ssid}` : "";

  return (
    <section className="wifi" aria-label="Wi-Fi">
      <h2>Wi-Fi</h2>
      {connected ? <p role="status">{connected}</p> : <p>Pick the house Wi-Fi.</p>}
      <ul>
        {(status?.networks ?? []).map((net) => (
          <li key={net.ssid}>
            <button type="button" onClick={() => setPicked(net)}>
              {net.ssid}
            </button>
          </li>
        ))}
      </ul>
      {picked ? (
        <form onSubmit={(event) => void join(event)}>
          <p>Join {picked.ssid}</p>
          {picked.secured ? (
            <input
              aria-label="Wi-Fi password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="off"
            />
          ) : null}
          <button type="submit" disabled={joining}>
            Join
          </button>
        </form>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
