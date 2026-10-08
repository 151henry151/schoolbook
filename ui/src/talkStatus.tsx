// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

export type TalkStatusKind = "listening" | "thinking" | "talking" | "paused" | "mic-error";

export function TalkStatus({
  kind,
  overVideo = false,
}: {
  kind: TalkStatusKind;
  overVideo?: boolean;
}) {
  if (kind !== "listening" && kind !== "thinking" && kind !== "mic-error") return null;
  const label = kind === "thinking" ? "thinking" : kind === "mic-error" ? "I cannot hear the microphone" : "listening";
  return (
    <div className={overVideo ? "status in-controls on-video" : "status in-controls"} role="status" aria-label={label}>
      {kind === "thinking" ? (
        <span className="status-brain" role="img" aria-label="thinking">
          <svg viewBox="0 0 64 64" aria-hidden="true">
            <path
              className="brain-lobe"
              d="M30 14c-3-5-12-6-17 0-4 2-6 7-5 12-5 3-6 11-1 16-1 6 3 11 10 12 3 1 6 0 9-2V14z"
              fill="#c47ab0"
            />
            <path
              className="brain-lobe"
              d="M34 14c3-5 12-6 17 0 4 2 6 7 5 12 5 3 6 11 1 16 1 6-3 11-10 12-3 1-6 0-9-2V14z"
              fill="#d48bc2"
            />
            <path
              d="M32 14v40M18 24c5 3 9 2 12 0M34 24c3 2 7 3 12 0M17 34c6 3 10 2 13 0M34 34c4 2 9 3 13 0M20 44c5 2 8 1 12-1M34 43c4 2 8 2 11 0"
              fill="none"
              stroke="#fff4fb"
              strokeWidth="2.2"
              strokeLinecap="round"
            />
          </svg>
        </span>
      ) : (
        <span className="status-ear" role="img" aria-label="listening">
          <svg viewBox="0 0 64 64" aria-hidden="true">
            <path
              d="M36 10c-12 0-20 9-20 22 0 10 5 16 10 20 2 2 4 6 2 10"
              fill="none"
              stroke="#e07a3d"
              strokeWidth="6"
              strokeLinecap="round"
            />
            <path
              d="M36 20c-6 0-10 5-10 12 0 6 3 9 6 11"
              fill="none"
              stroke="#e07a3d"
              strokeWidth="5"
              strokeLinecap="round"
            />
            <circle cx="38" cy="34" r="4" fill="#e07a3d" />
          </svg>
        </span>
      )}
    </div>
  );
}
