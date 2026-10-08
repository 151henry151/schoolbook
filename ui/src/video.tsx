// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useRef, useState } from "react";
import { embedUrl, playerCommand, songUrl, startEmbeddedPlayer, youtubePlayerReady, type PlayerTarget } from "./capture";
import { hideVideoCursor, VIDEO_CURSOR_IDLE_MS } from "./cursor";

export function VideoOverlay({
  videoId,
  paused = false,
  hidden = false,
  audioOnly = false,
  onClose,
  onPausedChange,
  player,
}: {
  videoId: string;
  paused?: boolean;
  hidden?: boolean;
  audioOnly?: boolean;
  onClose: () => void;
  onPausedChange?: (paused: boolean) => void;
  player?: PlayerTarget;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const [localPaused, setLocalPaused] = useState(paused);
  const [idle, setIdle] = useState(!paused);

  useEffect(() => {
    if (audioOnly) return;
    const node = frame.current;
    if (!node) return;
    function ready() {
      node?.contentWindow?.postMessage(JSON.stringify({ event: "listening", id: 1 }), "*");
    }
    node.addEventListener("load", ready);
    return () => node.removeEventListener("load", ready);
  }, [audioOnly, videoId]);

  useEffect(() => {
    if (audioOnly) return;
    function onMessage(event: MessageEvent) {
      if (event.origin && event.origin !== "https://www.youtube-nocookie.com") return;
      if (!youtubePlayerReady(event.data)) return;
      startEmbeddedPlayer(player ?? frame.current?.contentWindow ?? undefined);
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [audioOnly, player, videoId]);

  useEffect(() => {
    setLocalPaused(paused);
    setIdle(!paused);
    if (audioOnly) {
      const node = audio.current;
      if (!node) return;
      if (paused) node.pause();
      else void node.play().catch(() => {});
      return;
    }
    const target = player ?? frame.current?.contentWindow ?? undefined;
    if (!target) return;
    playerCommand(target, paused ? "pauseVideo" : "playVideo");
  }, [audioOnly, paused, player, videoId]);

  useEffect(() => {
    if (paused || idle) return;
    const timer = window.setTimeout(() => setIdle(true), VIDEO_CURSOR_IDLE_MS);
    return () => window.clearTimeout(timer);
  }, [paused, idle]);

  function toggle() {
    if (audioOnly) {
      const node = audio.current;
      if (localPaused) {
        void node?.play().catch(() => {});
        setLocalPaused(false);
        onPausedChange?.(false);
      } else {
        node?.pause();
        setLocalPaused(true);
        onPausedChange?.(true);
      }
      return;
    }
    const target = player ?? frame.current?.contentWindow ?? undefined;
    if (localPaused) {
      playerCommand(target, "playVideo");
      setLocalPaused(false);
      onPausedChange?.(false);
    } else {
      playerCommand(target, "pauseVideo");
      setLocalPaused(true);
      onPausedChange?.(true);
    }
  }

  return (
    <section
      className={[
        "video-overlay",
        hidden ? "is-hidden" : "",
        audioOnly ? "audio-only" : "",
        hideVideoCursor(paused, idle) ? "cursor-idle" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label={audioOnly ? "song" : "video"}
      onMouseMove={() => {
        if (!paused) setIdle(false);
      }}
    >
      {audioOnly ? (
        <audio ref={audio} src={songUrl(videoId)} autoPlay onEnded={onClose} />
      ) : (
        <iframe
          ref={frame}
          title="video"
          src={embedUrl(videoId)}
          allow="autoplay; fullscreen; encrypted-media"
        />
      )}
      {audioOnly ? (
        <div className="song-mark" aria-hidden="true">
          <svg viewBox="0 0 64 64">
            <circle cx="18" cy="48" r="8" fill="#e07a3d" />
            <circle cx="42" cy="42" r="8" fill="#e07a3d" />
            <path d="M26 48V16l24-6v32" fill="none" stroke="#e07a3d" strokeWidth="5" />
          </svg>
        </div>
      ) : null}
      <div
        className={audioOnly ? "video-cover song-cover" : "video-cover"}
        aria-label="pause or play"
        onClick={toggle}
      />
      <button
        type="button"
        className="video-close"
        aria-label="close video"
        onClick={(event) => {
          event.stopPropagation();
          onClose();
        }}
      >
        ×
      </button>
    </section>
  );
}
