// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useState, type FormEvent } from "react";

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

async function readJson(response: Response): Promise<unknown> {
  return response.json();
}

export function App() {
  const [authed, setAuthed] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [screen, setScreen] = useState<Screen>("Today");
  const [body, setBody] = useState<unknown>(null);

  async function login(event: FormEvent) {
    event.preventDefault();
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!response.ok) {
      const payload = (await readJson(response)) as { error?: string };
      setError(payload.error || "invalid password");
      return;
    }
    setAuthed(true);
    setPassword("");
    await openScreen("Today");
  }

  async function openScreen(next: Screen) {
    setScreen(next);
    const path: Record<Screen, string> = {
      Today: "/api/today",
      Sessions: "/api/sessions",
      Progress: "/api/progress",
      Memory: "/api/memory",
      Library: "/api/library/videos",
      Apps: "/api/apps",
      Session: "/api/today",
      Learner: "/api/learner",
      Settings: "/api/settings",
    };
    const response = await fetch(path[next]);
    if (!response.ok) {
      setAuthed(false);
      setBody(null);
      return;
    }
    setBody(await readJson(response));
  }

  async function post(path: string) {
    await fetch(path, { method: "POST" });
    await openScreen(screen);
  }

  if (!authed) {
    return (
      <main>
        <h1>Schoolbook</h1>
        <form onSubmit={(event) => void login(event)}>
          <label>
            Parent password
            <input
              aria-label="parent password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button type="submit">Unlock</button>
        </form>
        {error ? <p role="alert">{error}</p> : null}
      </main>
    );
  }

  return (
    <>
      <header>
        {SCREENS.map((name) => (
          <button key={name} type="button" onClick={() => void openScreen(name)}>
            {name}
          </button>
        ))}
      </header>
      <main>
        <h1>{screen}</h1>
        {screen === "Today" ? <TodayView data={body as Today | null} onResolve={(id) => void post(`/api/flags/${id}/resolve`)} /> : null}
        {screen === "Sessions" ? <SessionsView data={body} /> : null}
        {screen === "Progress" ? <ProgressView data={body} /> : null}
        {screen === "Memory" ? <MemoryView data={body} onForget={(kind, target) => void forget(kind, target, () => openScreen("Memory"))} /> : null}
        {screen === "Library" ? <LibraryView data={body} onBlock={(id) => void post(`/api/library/videos/${id}/block`)} /> : null}
        {screen === "Apps" ? <AppsView data={body} onDisable={(id) => void post(`/api/apps/${id}/disable`)} /> : null}
        {screen === "Session" ? (
          <section>
            <button type="button" onClick={() => void post("/api/session/pause")}>Pause</button>
            <button type="button" onClick={() => void post("/api/session/end")}>End</button>
            <button type="button" onClick={() => void post("/api/session/relock")}>Lock</button>
          </section>
        ) : null}
        {screen === "Learner" ? <LearnerView data={body} onSaved={() => void openScreen("Learner")} /> : null}
        {screen === "Settings" ? <SettingsView data={body} /> : null}
      </main>
    </>
  );
}

function TodayView({ data, onResolve }: { data: Today | null; onResolve: (id: string) => void }) {
  if (!data) return null;
  return (
    <section>
      <p>{data.in_session ? "In session" : "Idle"} · {data.minutes} minutes · {data.screen}</p>
      <p>{data.latest_summary}</p>
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
  const rows = Array.isArray(data) ? data : [];
  return (
    <ul>
      {rows.map((row) => {
        const item = row as { id: string; summary: string };
        return <li key={item.id}>{item.summary || item.id}</li>;
      })}
    </ul>
  );
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

function LearnerView({ data, onSaved }: { data: unknown; onSaved: () => void }) {
  const learner = (data ?? {}) as { first_name?: string; talk_mode?: string; voice?: string };
  const [name, setName] = useState(learner.first_name ?? "");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void fetch("/api/learner", {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ first_name: name, talk_mode: learner.talk_mode || "handsfree" }),
        }).then(onSaved);
      }}
    >
      <input aria-label="child name" value={name} onChange={(event) => setName(event.target.value)} />
      <p>Voice {learner.voice}. Talk mode {learner.talk_mode}.</p>
      <button type="submit">Save</button>
    </form>
  );
}

function SettingsView({ data }: { data: unknown }) {
  const settings = (data ?? {}) as { model?: string; lan?: boolean; keys_are_write_only?: boolean };
  const [key, setKey] = useState("");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void fetch("/api/settings", {
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

function forget(kind: string, target: string, refresh: () => Promise<void>) {
  void fetch("/api/memory/forget", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ kind, target }),
  }).then(() => refresh());
}
