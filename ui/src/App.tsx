// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useRef, useState } from "react";
import { Board } from "./board";
import { HOLD_MS, OFFLINE_APPS, holdComplete } from "./capture";
import { armed, armIfWaiting, stepHandsFree, type HandsFreeState } from "./handsfree";
import { createCaptureContext, startMic } from "./mic";
import { PlaybackQueue, decodePcm16, webAudioPlayer } from "./playback";
import { createVad, encodePcm16 } from "./pcm";
import { PROTOCOL_MAJOR, type BoardElement } from "./protocol";
import { ParentUnlock } from "./unlock";
import { TalkLines, nextTalkPair, spokenWordIndex, type TalkPair } from "./talkLines";
import { PictureOverlay } from "./picture";
import { VideoOverlay } from "./video";

type Phase = "home" | "talk";

type Choice = { id: string; label: string };

export function App() {
  const [phase, setPhase] = useState<Phase>("home");
  const [name, setName] = useState("friend");
  const [talk, setTalk] = useState<TalkPair>({ child: "", tutor: "" });
  const [spokenIndex, setSpokenIndex] = useState(-1);
  const talkRef = useRef<TalkPair>({ child: "", tutor: "" });
  const pendingVideo = useRef("");
  const pendingPicture = useRef("");
  const [elements, setElements] = useState<BoardElement[]>([]);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [videoId, setVideoId] = useState("");
  const [videoPaused, setVideoPaused] = useState(false);
  const [pictureId, setPictureId] = useState("");
  const [offline, setOffline] = useState(false);
  const [unlock, setUnlock] = useState(false);
  const [token, setToken] = useState("");
  const [draft, setDraft] = useState("");
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [status, setStatus] = useState("Listening");
  const [voice, setVoice] = useState("pipeline");
  const voiceRef = useRef("pipeline");
  const holdStarted = useRef<number | null>(null);
  const hands = useRef<HandsFreeState>(armed());
  const seq = useRef(0);
  const speaking = useRef(false);
  const queue = useRef(new PlaybackQueue(webAudioPlayer()));
  const socketRef = useRef<WebSocket | null>(null);
  const capture = useRef<AudioContext | null>(null);
  const vad = useRef(createVad());
  const dev = new URLSearchParams(window.location.search).has("dev");

  useEffect(() => {
    socketRef.current = socket;
  }, [socket]);

  useEffect(() => {
    voiceRef.current = voice;
  }, [voice]);

  useEffect(() => {
    talkRef.current = talk;
  }, [talk]);

  useEffect(() => {
    queue.current.setProgress((elapsed, duration) => {
      setSpokenIndex(spokenWordIndex(talkRef.current.tutor, elapsed, duration));
    });
    return () => queue.current.setProgress(null);
  }, []);

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
          role?: string;
          turn_id?: string;
          elements?: BoardElement[];
          video_id?: string;
          action?: string;
          image_id?: string;
          name?: string;
          options?: Choice[];
          pcm_b64?: string;
          sample_rate?: number;
          voice?: string;
          detail?: string;
        };
        if (message.type === "hello_ok") {
          if (message.learner_name) setName(message.learner_name);
          if (message.voice) setVoice(message.voice);
        }
        if (message.type === "transcript" && message.text) {
          setTalk((current) => nextTalkPair(current, message.role ?? "", message.text ?? ""));
          if (message.role === "tutor") {
            speaking.current = true;
            setStatus("Talking");
          }
        }
        if (message.type === "audio_chunk" && message.turn_id && message.pcm_b64) {
          speaking.current = true;
          setStatus("Talking");
          const pcm = decodePcm16(message.pcm_b64);
          if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
          if (pcm.length > 0) {
            void queue.current.enqueue(message.turn_id, pcm, message.sample_rate || 24000);
          }
        }
        if (message.type === "board" && message.elements) setElements(message.elements);
        if (message.type === "choices" && message.options && voiceRef.current !== "realtime") {
          setChoices(message.options);
        }
        if (message.type === "video" && message.action === "play" && message.video_id) {
          pendingVideo.current = message.video_id;
          void queue.current.whenIdle().then(() => {
            const ready = pendingVideo.current;
            if (!ready) return;
            pendingVideo.current = "";
            setPictureId("");
            setVideoPaused(false);
            setVideoId(ready);
          });
        }
        if (message.type === "video" && (message.action === "stop" || message.action === "destroy")) {
          pendingVideo.current = "";
          setPictureId("");
          setVideoPaused(false);
          setVideoId("");
        }
        if (message.type === "video" && message.action === "resume") {
          setPictureId("");
          setVideoPaused(false);
        }
        if (message.type === "picture" && message.image_id) {
          pendingPicture.current = message.image_id;
          void queue.current.whenIdle().then(() => {
            const ready = pendingPicture.current;
            if (!ready) return;
            pendingPicture.current = "";
            setPictureId(ready);
          });
        }
        if (message.type === "state" && message.name === "offline") setOffline(true);
        if (message.type === "state" && message.name === "home") setOffline(false);
        if (message.type === "state" && message.name === "parent_unlock") setUnlock(true);
        if (message.type === "state" && message.name === "thinking") setStatus("Thinking");
        if (message.type === "state" && message.name === "speaking") {
          speaking.current = true;
          setStatus("Talking");
        }
        if (message.type === "state" && message.name === "listening") {
          const finish = () => {
            speaking.current = false;
            hands.current = armIfWaiting(hands.current);
            if (message.detail === "hearing") setSpokenIndex(-1);
            setStatus(message.detail === "hearing" ? "I hear you" : "Listening");
          };
          if (message.detail === "hearing") {
            finish();
            return;
          }
          void queue.current.whenIdle().then(finish);
        }
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

  useEffect(() => {
    if (phase !== "talk" || (videoId && !videoPaused)) return;
    let stop: (() => void) | undefined;
    void startMic((pcm, dtMs) => {
      const ws = socketRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      if (voice === "realtime") {
        if (speaking.current || !queue.current.isIdle()) return;
        ws.send(
          JSON.stringify({
            type: "audio_frame",
            turn_id: "live",
            seq: seq.current,
            pcm_b64: encodePcm16(pcm),
            sample_rate: 16000,
          }),
        );
        seq.current += 1;
        return;
      }
      const hearing = vad.current(pcm);
      const result = stepHandsFree(
        hands.current,
        { voiced: hearing, dtMs, speaking: speaking.current },
        () => crypto.randomUUID(),
      );
      hands.current = result.state;
      const event = result.event;
      if (!event) return;
      if (event.type === "start" || event.type === "interrupt") {
        seq.current = 0;
        if (event.type === "interrupt") {
          queue.current.interrupt();
          speaking.current = false;
        }
        ws.send(JSON.stringify({ type: "talk_start", turn_id: event.turnId }));
        setStatus("I hear you");
      }
      if (event.type === "start" || event.type === "interrupt" || event.type === "frame") {
        if (event.type === "frame") setStatus(hearing ? "I hear you" : "Listening");
        ws.send(
          JSON.stringify({
            type: "audio_frame",
            turn_id: event.turnId,
            seq: seq.current,
            pcm_b64: encodePcm16(pcm),
            sample_rate: 16000,
          }),
        );
        seq.current += 1;
      }
      if (event.type === "end") {
        setStatus("Thinking");
        ws.send(JSON.stringify({ type: "talk_end", turn_id: event.turnId }));
      }
    }, capture.current ?? undefined)
      .then((value) => {
        stop = value;
      })
      .catch(() => {
        setStatus("I cannot hear the microphone");
      });
    return () => stop?.();
  }, [phase, voice, videoId, videoPaused]);

  function send(message: object) {
    socket?.send(JSON.stringify(message));
  }

  function sendText() {
    if (!draft.trim()) return;
    send({ type: "dev_text", turn_id: crypto.randomUUID(), text: draft });
    setDraft("");
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
        <button
          type="button"
          className="avatar"
          onClick={() => {
            try {
              const context = createCaptureContext();
              void context.resume();
              capture.current = context;
              vad.current = createVad();
              hands.current = armed();
            } catch {
              capture.current = null;
            }
            setPhase("talk");
          }}
        >
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
        className={videoId ? "hold-corner hold-left" : "hold-corner"}
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
      <TalkLines
        name={name}
        child={talk.child}
        tutor={talk.tutor}
        spokenIndex={spokenIndex}
        overVideo={Boolean((videoId && videoPaused) || pictureId)}
      />
      <p className={(videoId && videoPaused) || pictureId ? "status on-video" : "status"} role="status">
        {status}
      </p>
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
      {pictureId ? (
        <PictureOverlay
          imageId={pictureId}
          onClose={() => {
            setPictureId("");
          }}
        />
      ) : null}
      {videoId ? (
        <VideoOverlay
          videoId={videoId}
          paused={videoPaused}
          hidden={Boolean(pictureId)}
          onClose={() => {
            setPictureId("");
            setVideoPaused(false);
            setVideoId("");
            send({ type: "video_ui", action: "done" });
          }}
          onPausedChange={(paused) => {
            setVideoPaused(paused);
            send({ type: "video_ui", action: paused ? "pause" : "resume" });
          }}
        />
      ) : null}
      {unlock ? <ParentUnlock token={token} /> : null}
    </main>
  );
}
