// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useState } from "react";
import { Board } from "./board";
import { PROTOCOL_MAJOR, type BoardElement } from "./protocol";

type Phase = "home" | "talk";

export function App() {
  const [phase, setPhase] = useState<Phase>("home");
  const [name, setName] = useState("friend");
  const [transcript, setTranscript] = useState("");
  const [elements, setElements] = useState<BoardElement[]>([]);
  const [draft, setDraft] = useState("");
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const dev = new URLSearchParams(window.location.search).has("dev");

  useEffect(() => {
    let active = true;
    let opened: WebSocket | null = null;
    void (async () => {
      const response = await fetch("/token");
      const body = (await response.json()) as { token: string };
      if (!active) return;
      const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
      opened = ws;
      ws.onmessage = (event) => {
        const message = JSON.parse(String(event.data)) as {
          type: string;
          learner_name?: string;
          text?: string;
          elements?: BoardElement[];
        };
        if (message.type === "hello_ok" && message.learner_name) setName(message.learner_name);
        if (message.type === "transcript" && message.text) setTranscript(message.text);
        if (message.type === "board" && message.elements) setElements(message.elements);
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

  function sendText() {
    if (!socket || !draft.trim()) return;
    socket.send(JSON.stringify({ type: "dev_text", turn_id: crypto.randomUUID(), text: draft }));
    setDraft("");
  }

  if (phase === "home") {
    return (
      <main className="home">
        <button type="button" className="avatar" onClick={() => setPhase("talk")}>
          {name}
        </button>
      </main>
    );
  }

  return (
    <main className="talk">
      <Board elements={elements} />
      <p className="transcript">{transcript}</p>
      <button type="button" className="talk-button" aria-label="talk">
        Talk
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
      <section className="video-overlay" aria-label="video controls" hidden>
        <button type="button">Play</button>
        <button type="button">Pause</button>
        <button type="button">Done</button>
      </section>
    </main>
  );
}
