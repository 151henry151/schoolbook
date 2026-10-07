// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { embedUrl } from "./capture";

export function VideoOverlay({ videoId, onDone }: { videoId: string; onDone: () => void }) {
  return (
    <section className="video-overlay" aria-label="video controls">
      <iframe title="video" src={embedUrl(videoId)} allow="autoplay" />
      <div className="video-cover">
        <button type="button">Play</button>
        <button type="button">Pause</button>
        <button type="button" onClick={onDone}>
          Done
        </button>
      </div>
    </section>
  );
}
