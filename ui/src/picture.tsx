// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

export function PictureOverlay({
  imageId,
  loading = false,
  onClose,
}: {
  imageId: string;
  loading?: boolean;
  onClose: () => void;
}) {
  return (
    <section className="picture-overlay above-controls" aria-label="picture">
      <div className="picture-frame">
        {loading ? (
          <div className="picture-loading" role="status" aria-label="making a picture">
            <div className="picture-placeholder" />
            <div className="picture-spinner" />
          </div>
        ) : (
          <img className="picture-fit" src={`/pictures/${imageId}`} alt={imageId} />
        )}
      </div>
      <button type="button" className="video-close" aria-label="close picture" onClick={onClose}>
        ×
      </button>
    </section>
  );
}
