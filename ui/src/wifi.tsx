// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useRef, useState, type FormEvent } from "react";

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
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/wifi", { cache: "no-store" });
      const body = (await response.json()) as Status;
      setStatus(body);
      if (!response.ok) setError(body.error || "Wi-Fi is not ready");
    } catch {
      setError("Cannot reach Wi-Fi settings. Try refreshing.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function join(event: FormEvent) {
    event.preventDefault();
    if (!picked) return;
    setJoining(true);
    setError("");
    try {
      const response = await fetch("/wifi/connect", {
        method: "POST",
        headers: { "content-type": "application/json", "x-schoolbook-token": token },
        body: JSON.stringify({ ssid: picked.ssid, password }),
      });
      const body = (await response.json()) as Status & { ok?: boolean };
      if (!response.ok) {
        setError(body.error || "could not join");
        return;
      }
      setStatus(body);
      setPicked(null);
      setPassword("");
    } catch {
      setError("Connection changed or was interrupted. Refresh to check Wi-Fi.");
    } finally {
      setJoining(false);
    }
  }

  const connected = status?.ssid && status.connected ? `Connected to ${status.ssid}` : "";

  return (
    <section className="wifi" aria-label="Wi-Fi">
      <h2>Wi-Fi</h2>
      <button type="button" disabled={loading || joining} onClick={() => void load()}>
        {loading ? "Looking for networks…" : "Refresh networks"}
      </button>
      {connected ? <p role="status">{connected}</p> : <p>Pick the house Wi-Fi.</p>}
      <ul>
        {(status?.networks ?? []).map((net) => (
          <li key={net.ssid}>
            <button type="button" disabled={joining} onClick={() => { setPicked(net); setPassword(""); }}>
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
            {joining ? "Joining…" : "Join"}
          </button>
        </form>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}

export function WifiButton({ token, onOpen }: { token: string; onOpen?: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="wifi-button" aria-label="Wi-Fi settings"
        onClick={() => { onOpen?.(); setOpen(true); dialog.current?.showModal(); }}>
        <svg viewBox="0 0 32 28" aria-hidden="true">
          <path d="M3 9a20 20 0 0 1 26 0M7 15a14 14 0 0 1 18 0M12 21a6 6 0 0 1 8 0"
            fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
          <circle cx="16" cy="26" r="2" fill="currentColor" />
        </svg>
        <span>Wi-Fi</span>
      </button>
      <dialog ref={dialog} className="wifi-dialog" aria-label="Wi-Fi settings"
        onClose={() => setOpen(false)}>
        <button type="button" className="wifi-close" aria-label="Close Wi-Fi settings"
          onClick={() => { dialog.current?.close(); setOpen(false); }}>×</button>
        {open ? <WifiSetup token={token} /> : null}
      </dialog>
    </>
  );
}
