// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

export function PictureOverlay({ imageId, onClose }: { imageId: string; onClose: () => void }) {
  return (
    <section className="picture-overlay" aria-label="picture">
      <img src={`/pictures/${imageId}`} alt={imageId} />
      <button type="button" className="video-close" aria-label="close picture" onClick={onClose}>
        ×
      </button>
    </section>
  );
}
