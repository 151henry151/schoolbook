// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

export const VIDEO_CURSOR_IDLE_MS = 2000;

export function hideVideoCursor(paused: boolean, idle: boolean): boolean {
  return !paused && idle;
}

const POINTER_SVG = encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
    <path fill="#fff" stroke="#2a6f7f" stroke-width="3.5" stroke-linejoin="round"
      d="M6 4 L6 38 L16 28 L22 42 L28 39 L22 26 L38 24 Z"/>
  </svg>`,
);

export const POINTER_CURSOR = `cursor: url("data:image/svg+xml,${POINTER_SVG}") 6 2, auto`;

export function cartoonCursorCss(): string {
  return [
    `html, body, button, .talk, .home, .video-overlay, .picture-overlay, .app-overlay, .unlock { ${POINTER_CURSOR}; }`,
    `.video-overlay.cursor-idle, .video-overlay.cursor-idle * { cursor: none !important; }`,
  ].join("\n");
}
