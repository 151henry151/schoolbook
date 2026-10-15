// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, jsonBody, request } from "./api";
import { formatEasternTime } from "./time";

const SCREENS = ["Today", "Sessions", "Progress", "Memory", "Library", "Apps", "Session", "Learner", "Settings"] as const;
type Screen = (typeof SCREENS)[number];

type Flag = { id: string; reason: string; severity: string; excerpt: string };
type Today = {
  in_session: boolean;
  paused: boolean;
  screen: string;
  minutes: number;
  open_flags: Flag[];
  latest_summary: string;
  model_calls: number;
  spend_alert_cents: number;
};

export function App() {
  const [authed, setAuthed] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [screen, setScreen] = useState<Screen>("Today");
  const [body, setBody] = useState<unknown>(null);

  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const revision = useRef(0);

  function failure(err: unknown) {
    setError(err instanceof Error ? err.message : "Please try again.");
    if (err instanceof ApiError && err.status === 401) {
      setAuthed(false);
      setBody(null);
    }
  }

  useEffect(() => { void openScreen("Today", true); }, []);

  async function login(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await request("api/login", jsonBody({ password }));
      setPassword("");
      await openScreen("Today");
    } catch (err) { failure(err); }
    finally { setBusy(false); }
  }

  async function openScreen(next: Screen, restore = false) {
    const current = ++revision.current;
    setScreen(next);
    setBody(null);
    setError("");
    setBusy(true);
    const path: Record<Screen, string> = {
      Today: "api/today", Sessions: "api/sessions", Progress: "api/progress",
      Memory: "api/memory", Library: "api/library/videos", Apps: "api/apps",
      Session: "api/today", Learner: "api/learner", Settings: "api/settings",
    };
    try {
      const data = await request(path[next]);
      if (current !== revision.current) return;
      setAuthed(true);
      setBody(data);
    } catch (err) {
      if (current === revision.current && !(restore && err instanceof ApiError && err.status === 401)) failure(err);
    } finally { if (current === revision.current) setBusy(false); }
  }

  async function save(path: string, init: RequestInit = { method: "POST" }) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await request(path, init);
      if (path.endsWith("/relock")) { setAuthed(false); setBody(null); return; }
      setNotice("Saved.");
      await openScreen(screen);
    } catch (err) { failure(err); }
    finally { setBusy(false); }
  }
  function post(path: string) { void save(path); }

  if (!authed) {
    return (
      <main className="login-card">
        <p className="eyebrow">PARENT CONSOLE</p><h1>Schoolbook</h1>
        <p>A little window into your child’s learning.</p>
        <form onSubmit={(event) => void login(event)}>
          <label>
            Parent password
            <input
              aria-label="parent password"
              type="password" autoComplete="current-password" required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button type="submit" disabled={busy}>Unlock</button>
        </form>
        {error ? <p role="alert">{error}</p> : null}
      </main>
    );
  }

  return (
    <>
      <header className="brand"><div><strong>Schoolbook</strong><span>Parent console</span></div>
        <button disabled={busy} onClick={() => post("api/session/relock")}>Lock console</button>
      </header>
      <div className="layout"><nav aria-label="Parent console">
        {SCREENS.map((name) => (
          <button key={name} type="button" aria-current={screen === name ? "page" : undefined} disabled={busy} onClick={() => { setNotice(""); void openScreen(name); }}>
            {name}
          </button>
        ))}
      </nav>
      <main>
        <div className="page-heading"><h1>{screen}</h1><button disabled={busy} onClick={() => void openScreen(screen)}>Refresh</button></div>
        {error ? <p role="alert">{error}</p> : null}
        {notice ? <p role="status">{notice}</p> : null}
        {busy ? <p role="status">Connecting…</p> : null}
        <fieldset disabled={busy} className="content">
        {screen === "Today" ? <TodayView data={body as Today | null} onResolve={(id) => void post(`/api/flags/${id}/resolve`)} /> : null}
        {screen === "Sessions" ? <SessionsView data={body} /> : null}
        {screen === "Progress" ? <ProgressView data={body} /> : null}
        {screen === "Memory" ? <MemoryView data={body} onForget={(kind, target) => { if (window.confirm("Forget this saved note?")) void save("api/memory/forget", jsonBody({ kind, target })); }} /> : null}
        {screen === "Library" ? <LibraryView data={body} onBlock={(id) => void post(`/api/library/videos/${id}/block`)} /> : null}
        {screen === "Apps" ? <AppsView data={body} onDisable={(id) => void post(`/api/apps/${id}/disable`)} /> : null}
        {screen === "Session" ? (
          <section>
            <h2>End the child’s session</h2><p>This closes Schoolbook on the laptop. Use this when your child is finished.</p><button type="button" onClick={() => { if (window.confirm("End the child’s session and close Schoolbook?")) post("api/session/end"); }}>End session</button>
            <button type="button" onClick={() => void post("/api/session/relock")}>Lock</button>
          </section>
        ) : null}
        {screen === "Learner" && body ? <LearnerView data={body} onSave={save} /> : null}
        {screen === "Settings" && body ? <SettingsView data={body} onSave={save} /> : null}
        </fieldset>
      </main></div>
    </>
  );
}

function TodayView({ data, onResolve }: { data: Today | null; onResolve: (id: string) => void }) {
  if (!data) return null;
  return (
    <section>
      <div className="metrics"><article><span>Right now</span><strong>{data.in_session ? "Learning" : "Idle"}</strong><small>{data.screen}</small></article><article><span>Session time</span><strong>{data.minutes} min</strong></article><article><span>Needs attention</span><strong>{data.open_flags.length}</strong></article></div><h2>Latest update</h2>
      <p>{data.latest_summary || "A summary will appear after a session."}</p>
      <p>Model calls {data.model_calls}. Spend alert {data.spend_alert_cents} cents.</p>
      {data.open_flags.map((flag) => (
        <article key={flag.id} className="flag">
          <p>{flag.severity}: {flag.reason}</p>
          <p>{flag.excerpt}</p>
          <button type="button" onClick={() => onResolve(flag.id)}>Resolve</button>
        </article>
      ))}
    </section>
  );
}

function SessionsView({ data }: { data: unknown }) {
  const [detail, setDetail] = useState<{ turns: { role: string; text: string }[] } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const rows = Array.isArray(data) ? [...data].reverse() : [];
  async function inspect(id: string) {
    setLoading(true); setError("");
    try { setDetail(await request(`api/sessions/${encodeURIComponent(id)}`) as typeof detail); }
    catch (err) { setError(err instanceof Error ? err.message : "Cannot load this session."); }
    finally { setLoading(false); }
  }
  if (detail) return <section><button onClick={() => setDetail(null)}>Back to sessions</button><h2>Conversation</h2>{detail.turns.length ? detail.turns.map((turn, i) => <article className="conversation" key={i}><strong>{turn.role}</strong><p>{turn.text}</p></article>) : <p>No saved conversation yet.</p>}</section>;
  return <section>{error && <p role="alert">{error}</p>}{loading && <p role="status">Loading conversation…</p>}
    {rows.length ? <ul>{rows.map((item: { id: string; summary: string; started_at?: string }) => <li key={item.id}>
      <small>{item.started_at ? formatEasternTime(item.started_at) : "Session"}</small><p>{item.summary || "Session in progress"}</p>
      <button disabled={loading} onClick={() => void inspect(item.id)}>Read conversation</button></li>)}</ul> : <p>No sessions yet.</p>}</section>;
}

function ProgressView({ data }: { data: unknown }) {
  const skills = (data as { skills?: { id: string; title: string; state: string }[] } | null)?.skills ?? [];
  return (
    <ul>
      {skills.map((skill) => (
        <li key={skill.id}>{skill.title}: {skill.state}</li>
      ))}
    </ul>
  );
}

function MemoryView({
  data,
  onForget,
}: {
  data: unknown;
  onForget: (kind: string, target: string) => void;
}) {
  const memory = data as { notes?: { id: string; text: string }[]; interests?: { topic: string }[] } | null;
  return (
    <section>
      {(memory?.notes ?? []).map((note) => (
        <p key={note.id}>
          {note.text} <button type="button" onClick={() => onForget("note", note.id)}>Forget</button>
        </p>
      ))}
      {(memory?.interests ?? []).map((interest) => (
        <p key={interest.topic}>{interest.topic}</p>
      ))}
    </section>
  );
}

function LibraryView({ data, onBlock }: { data: unknown; onBlock: (id: string) => void }) {
  const videos = Array.isArray(data) ? data : [];
  return (
    <ul>
      {videos.map((row) => {
        const video = row as { id: string; title: string; verdict: string; reasons: string };
        return (
          <li key={video.id}>
            {video.title} · {video.verdict} · {video.reasons}
            <button type="button" onClick={() => onBlock(video.id)}>Block</button>
          </li>
        );
      })}
    </ul>
  );
}

function AppsView({ data, onDisable }: { data: unknown; onDisable: (id: string) => void }) {
  const apps = Array.isArray(data) ? data : [];
  return (
    <ul>
      {apps.map((row) => {
        const app = row as { id: string; name: string; enabled: boolean };
        return (
          <li key={app.id}>
            {app.name} {app.enabled ? "on" : "off"}
            <button type="button" onClick={() => onDisable(app.id)}>Disable</button>
          </li>
        );
      })}
    </ul>
  );
}

type Save = (path: string, init: RequestInit) => Promise<void>;

function LearnerView({ data, onSave }: { data: unknown; onSave: Save }) {
  const learner = (data ?? {}) as { first_name?: string; talk_mode?: string; voice?: string };
  const [name, setName] = useState(learner.first_name ?? "");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void onSave("api/learner", {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ first_name: name, talk_mode: learner.talk_mode || "handsfree" }),
        });
      }}
    >
      <input aria-label="child name" value={name} onChange={(event) => setName(event.target.value)} />
      <p>Voice {learner.voice}. Talk mode {learner.talk_mode}.</p>
      <button type="submit">Save</button>
    </form>
  );
}

function SettingsView({ data, onSave }: { data: unknown; onSave: Save }) {
  const settings = (data ?? {}) as { model?: string; lan?: boolean; keys_are_write_only?: boolean };
  const [key, setKey] = useState("");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void onSave("api/settings", {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ anthropic_api_key: key }),
        });
        setKey("");
      }}
    >
      <p>Model {settings.model}. LAN {settings.lan ? "on" : "off"}.</p>
      <label>
        Anthropic API key
        <input aria-label="anthropic api key" type="password" value={key} onChange={(event) => setKey(event.target.value)} />
      </label>
      <button type="submit">Save key</button>
      {settings.keys_are_write_only ? <p>Keys are write-only.</p> : null}
    </form>
  );
}
