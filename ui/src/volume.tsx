// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useState } from "react";

const STORAGE_KEY = "schoolbook.media-volume";

function savedVolume(): number {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === null || saved.trim() === "") return 100;
    const value = Number(saved);
    return Number.isFinite(value) && value >= 0 && value <= 100 ? Math.round(value) : 100;
  } catch {
    return 100;
  }
}

export function useMediaVolume(): [number, (value: number) => void] {
  const [volume, setVolume] = useState(savedVolume);
  function changeVolume(value: number) {
    if (!Number.isFinite(value)) return;
    const next = Math.max(0, Math.min(100, Math.round(value)));
    setVolume(next);
    try {
      localStorage.setItem(STORAGE_KEY, String(next));
    } catch {
      // Volume still works if browser storage is unavailable.
    }
  }
  return [volume, changeVolume];
}

export function VolumeControls({ volume, onChange }: { volume: number; onChange: (value: number) => void }) {
  return (
    <div className="media-volume" role="group" aria-label="Playback volume">
      <svg className="volume-speaker" viewBox="0 0 32 32" aria-hidden="true">
        <path d="M3 12H9L17 5V27L9 20H3Z" fill="currentColor" />
        {volume === 0 ? <path d="M22 12L29 20M29 12L22 20" /> : <>
          <path d="M21 11Q26 16 21 21" />
          {volume > 50 ? <path d="M25 6Q34 16 25 26" /> : null}
        </>}
      </svg>
      <button type="button" aria-label="Volume down" disabled={volume === 0}
        onClick={() => onChange(volume - 10)}>−</button>
      <input type="range" aria-label="Playback volume" aria-valuetext={volume === 0 ? "Muted" : `${volume}%`}
        min="0" max="100" step="1" value={volume}
        onChange={(event) => onChange(Number(event.target.value))} />
      <button type="button" aria-label="Volume up" disabled={volume === 100}
        onClick={() => onChange(volume + 10)}>+</button>
      <output aria-hidden="true">{volume}%</output>
    </div>
  );
}
