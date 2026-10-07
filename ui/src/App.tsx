// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useRef, useState } from "react";
import { Board } from "./board";
import { HOLD_MS, OFFLINE_APPS, holdComplete } from "./capture";
import { PROTOCOL_MAJOR, type BoardElement } from "./protocol";
import { ParentUnlock } from "./unlock";
import { VideoOverlay } from "./video";

type Phase = "home" | "talk";

type Choice = { id: string; label: string };

export function App() {
  const [phase, setPhase] = useState<Phase>("home");
  const [name, setName] = useState("friend");
  const [transcript, setTranscript] = useState("");
  const [elements, setElements] = useState<BoardElement[]>([]);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [videoId, setVideoId] = useState("");
  const [offline, setOffline] = useState(false);
  const [unlock, setUnlock] = useState(false);
  const [token, setToken] = useState("");
  const [draft, setDraft] = useState("");
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [listening, setListening] = useState(false);
  const holdStarted = useRef<number | null>(null);
  const dev = new URLSearchParams(window.location.search).has("dev");

  useEffect(() => {
    let active = true;
    let opened: WebSocket | null = null;
    void (async () => {
      const response = await fetch("/token");
      if (!response.ok) return;
      const body = (await response.json()) as { token: string };
      if (!active) return;
      setToken(body.token);
      const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
      opened = ws;
      ws.onmessage = (event) => {
        const message = JSON.parse(String(event.data)) as {
          type: string;
          learner_name?: string;
          text?: string;
          elements?: BoardElement[];
          video_id?: string;
          action?: string;
          name?: string;
          options?: Choice[];
        };
        if (message.type === "hello_ok" && message.learner_name) setName(message.learner_name);
        if (message.type === "transcript" && message.text) {
          setTranscript(message.text);
          setListening(false);
        }
        if (message.type === "board" && message.elements) setElements(message.elements);
        if (message.type === "choices" && message.options) setChoices(message.options);
        if (message.type === "video" && message.action === "play" && message.video_id) setVideoId(message.video_id);
        if (message.type === "video" && (message.action === "stop" || message.action === "destroy")) setVideoId("");
        if (message.type === "state" && message.name === "offline") setOffline(true);
        if (message.type === "state" && message.name === "home") setOffline(false);
        if (message.type === "state" && message.name === "parent_unlock") setUnlock(true);
        if (message.type === "state" && message.name === "listening") setListening(true);
      };
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: "hello", protocol_major: PROTOCOL_MAJOR, token: body.token }));
        setSocket(ws);
      };
    })();
    return () => {
      active = false;
      opened?.close();
    };
  }, []);

  function send(message: object) {
    socket?.send(JSON.stringify(message));
  }

  function sendText() {
    if (!draft.trim()) return;
    send({ type: "dev_text", turn_id: crypto.randomUUID(), text: draft });
    setDraft("");
  }

  function toggleTalk() {
    const turnId = crypto.randomUUID();
    if (!listening) {
      setListening(true);
      send({ type: "talk_start", turn_id: turnId });
      sessionStorage.setItem("schoolbook-turn", turnId);
      return;
    }
    const current = sessionStorage.getItem("schoolbook-turn") || turnId;
    send({ type: "talk_end", turn_id: current });
    setListening(false);
  }

  function finishHold() {
    const started = holdStarted.current;
    holdStarted.current = null;
    if (started !== null && holdComplete(Date.now() - started)) {
      setUnlock(true);
      send({ type: "unlock_gesture" });
    }
  }

  if (phase === "home") {
    return (
      <main className="home">
        <button type="button" className="avatar" onClick={() => setPhase("talk")}>
          {name}
        </button>
        <p>I am a computer helper.</p>
      </main>
    );
  }

  return (
    <main className="talk">
      <button
        type="button"
        className="hold-corner"
        aria-label="parent corner"
        onPointerDown={() => {
          holdStarted.current = Date.now();
          window.setTimeout(finishHold, HOLD_MS);
        }}
        onPointerUp={finishHold}
      />
      <Board elements={elements} />
      {choices.length > 0 ? (
        <div className="choices">
          {choices.map((choice) => (
            <button
              key={choice.id}
              type="button"
              onClick={() => {
                send({ type: "choice", turn_id: crypto.randomUUID(), option_id: choice.id });
                setChoices([]);
              }}
            >
              {choice.label}
            </button>
          ))}
        </div>
      ) : null}
      <p className="transcript">{transcript}</p>
      {offline ? (
        <section aria-label="offline apps">
          <p>The tutor is resting.</p>
          {OFFLINE_APPS.map((app) => (
            <button key={app} type="button">
              {app}
            </button>
          ))}
        </section>
      ) : null}
      <button type="button" className="talk-button" aria-label="talk" onClick={toggleTalk}>
        {listening ? "Stop" : "Talk"}
      </button>
      <button type="button" className="home-button" onClick={() => send({ type: "home" })}>
        Home
      </button>
      {dev ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            sendText();
          }}
        >
          <input aria-label="dev text" value={draft} onChange={(event) => setDraft(event.target.value)} />
          <button type="submit">Send</button>
        </form>
      ) : null}
      {videoId ? <VideoOverlay videoId={videoId} onDone={() => { setVideoId(""); send({ type: "video_ui", action: "done" }); }} /> : null}
      {unlock ? <ParentUnlock token={token} /> : null}
    </main>
  );
}
