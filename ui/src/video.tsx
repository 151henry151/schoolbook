// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  embedUrl,
  playerCommand,
  songUrl,
  startEmbeddedPlayer,
  youtubePlayerEnded,
  youtubePlayerReady,
  type PlayerTarget,
} from "./capture";
import { VideoWatchTracker } from "./videoWatch";
import { hideVideoCursor, VIDEO_CURSOR_IDLE_MS } from "./cursor";
import { useMediaVolume, VolumeControls } from "./volume";

export function VideoOverlay({
  videoId,
  paused = false,
  hidden = false,
  audioOnly = false,
  onClose,
  onEnded,
  onPlaying,
  onWatched,
  onPausedChange,
  player,
}: {
  videoId: string;
  paused?: boolean;
  hidden?: boolean;
  audioOnly?: boolean;
  onClose: () => void;
  onEnded?: () => void;
  onPlaying?: () => void;
  onWatched?: (progress: { watched_s: number; duration_s: number }) => void;
  onPausedChange?: (paused: boolean) => void;
  player?: PlayerTarget;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const finished = useRef(false);
  const watch = useRef(new VideoWatchTracker());
  const watchedCallback = useRef(onWatched);
  watchedCallback.current = onWatched;
  useEffect(() => { watch.current = new VideoWatchTracker(); finished.current = false; }, [videoId]);
  const [localPaused, setLocalPaused] = useState(paused);
  const [idle, setIdle] = useState(!paused);
  const [volume, changeVolume] = useMediaVolume();
  const volumeRef = useRef(volume);
  volumeRef.current = volume;

  function finish(reason: "close" | "ended") {
    if (finished.current) return;
    finished.current = true;
    if (reason === "ended") (onEnded ?? onClose)();
    else onClose();
  }

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
      if (event.source && event.source !== frame.current?.contentWindow) return;
      const progress = watch.current.update(event.data, performance.now());
      if (progress) watchedCallback.current?.(progress);
      if (youtubePlayerEnded(event.data)) {
        finish("ended");
        return;
      }
      if (!youtubePlayerReady(event.data)) return;
      startEmbeddedPlayer(player ?? frame.current?.contentWindow ?? undefined, volumeRef.current);
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [audioOnly, player, videoId]);

  useLayoutEffect(() => {
    if (audioOnly) {
      if (audio.current) audio.current.volume = volume / 100;
    } else {
      const target = player ?? frame.current?.contentWindow ?? undefined;
      playerCommand(target, "setVolume", [volume]);
      playerCommand(target, "unMute");
    }
  }, [audioOnly, player, videoId, volume]);

  useEffect(() => {
    setLocalPaused(paused);
    setIdle(!paused);
    if (audioOnly) {
      const node = audio.current;
      if (!node) return;
      if (paused) node.pause();
      else void Promise.resolve(node.play()).catch(() => { setLocalPaused(true); onPausedChange?.(true); });
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
        void Promise.resolve(node?.play()).catch(() => { setLocalPaused(true); onPausedChange?.(true); });
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
        !audioOnly && hideVideoCursor(paused, idle) ? "cursor-idle" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label={audioOnly ? "song" : "video"}
      onMouseMove={() => {
        if (!paused) setIdle(false);
      }}
    >
      {audioOnly ? (
        <audio ref={audio} src={songUrl(videoId)} autoPlay onPlaying={onPlaying} onError={() => { setLocalPaused(true); onPausedChange?.(true); }} onEnded={() => finish("ended")} />
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
      {audioOnly ? <button type="button" className="song-toggle" aria-label={localPaused ? "Play music" : "Pause music"} onClick={toggle}>
        <svg viewBox="0 0 48 48" aria-hidden="true">{localPaused ? <path d="M15 8L39 24 15 40Z" fill="currentColor" /> : <><rect x="12" y="9" width="9" height="30" rx="2" fill="currentColor" /><rect x="27" y="9" width="9" height="30" rx="2" fill="currentColor" /></>}</svg>
      </button> : null}
      <VolumeControls volume={volume} onChange={changeVolume} />
      <button
        type="button"
        className="video-close"
        aria-label="close video"
        onClick={(event) => {
          event.stopPropagation();
          finish("close");
        }}
      >
        ×
      </button>
    </section>
  );
}
