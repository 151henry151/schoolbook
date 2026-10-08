// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useRef, useState } from "react";
import { embedUrl, playerCommand, type PlayerTarget } from "./capture";
import { hideVideoCursor, VIDEO_CURSOR_IDLE_MS } from "./cursor";

export function VideoOverlay({
  videoId,
  paused = false,
  hidden = false,
  onClose,
  onPausedChange,
  player,
}: {
  videoId: string;
  paused?: boolean;
  hidden?: boolean;
  onClose: () => void;
  onPausedChange?: (paused: boolean) => void;
  player?: PlayerTarget;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [localPaused, setLocalPaused] = useState(paused);
  const [idle, setIdle] = useState(!paused);

  useEffect(() => {
    const node = frame.current;
    if (!node) return;
    function ready() {
      node?.contentWindow?.postMessage(JSON.stringify({ event: "listening", id: 1 }), "*");
    }
    node.addEventListener("load", ready);
    return () => node.removeEventListener("load", ready);
  }, [videoId]);

  useEffect(() => {
    setLocalPaused(paused);
    setIdle(!paused);
    const target = player ?? frame.current?.contentWindow ?? undefined;
    if (!target) return;
    playerCommand(target, paused ? "pauseVideo" : "playVideo");
  }, [paused, player, videoId]);

  useEffect(() => {
    if (paused || idle) return;
    const timer = window.setTimeout(() => setIdle(true), VIDEO_CURSOR_IDLE_MS);
    return () => window.clearTimeout(timer);
  }, [paused, idle]);

  function toggle() {
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
        hideVideoCursor(paused, idle) ? "cursor-idle" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label="video"
      onMouseMove={() => {
        if (!paused) setIdle(false);
      }}
    >
      <iframe ref={frame} title="video" src={embedUrl(videoId)} allow="autoplay; fullscreen" />
      <div className="video-cover" aria-label="pause or play" onClick={toggle} />
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
