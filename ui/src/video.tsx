// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useRef, useState } from "react";
import { embedUrl, playerCommand, type PlayerTarget } from "./capture";

export function VideoOverlay({
  videoId,
  onClose,
  player,
}: {
  videoId: string;
  onClose: () => void;
  player?: PlayerTarget;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const node = frame.current;
    if (!node) return;
    function ready() {
      node?.contentWindow?.postMessage(JSON.stringify({ event: "listening", id: 1 }), "*");
    }
    node.addEventListener("load", ready);
    return () => node.removeEventListener("load", ready);
  }, [videoId]);

  function toggle() {
    const target = player ?? frame.current?.contentWindow ?? undefined;
    if (paused) {
      playerCommand(target, "playVideo");
      setPaused(false);
    } else {
      playerCommand(target, "pauseVideo");
      setPaused(true);
    }
  }

  return (
    <section className="video-overlay" aria-label="video">
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
