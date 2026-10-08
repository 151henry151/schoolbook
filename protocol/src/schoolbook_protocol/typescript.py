# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Emit TypeScript interfaces that mirror the protocol models."""

from __future__ import annotations

from schoolbook_protocol.version import MAJOR

_LINES = [
    "// SPDX-" + "License-Identifier: GPL-3.0-or-later",
    "// SPDX-" + "FileCopyrightText: 2026 Schoolbook contributors",
    "",
    "/** Generated from schoolbook_protocol. Do not edit by hand. */",
    f"export const PROTOCOL_MAJOR = {MAJOR};",
    "",
    "export type BoardElement =",
    '  | { type: "big_text"; text: string; highlights: number[] }',
    '  | { type: "letter_tiles"; letters: string[] }',
    '  | { type: "number"; value: string }',
    '  | { type: "equation"; text: string }',
    '  | { type: "dots"; count: number; emoji: string }',
    '  | { type: "objects"; count: number; emoji: string | null;',
    "      image_id: string | null }",
    '  | { type: "number_line"; start: number; end: number;',
    "      marks: number[]; hops: { start: number; end: number }[] }",
    '  | { type: "image"; image_id: string }',
    '  | { type: "shapes"; items: { shape: "circle" | "square"',
    '      | "triangle" | "star"; color: string }[] };',
    "",
    "export type ClientMessage =",
    '  | { type: "hello"; protocol_major: number; token: string }',
    '  | { type: "audio_frame"; turn_id: string; seq: number;',
    "      pcm_b64: string; sample_rate: number }",
    '  | { type: "talk_start"; turn_id: string }',
    '  | { type: "talk_end"; turn_id: string }',
    '  | { type: "dev_text"; turn_id: string; text: string }',
    '  | { type: "choice"; turn_id: string; option_id: string }',
    '  | { type: "board_tap"; turn_id: string;',
    "      element_index: number; index: number }",
    '  | { type: "video_ui"; action: "pause" | "resume" | "done" }',
    '  | { type: "unlock_gesture" }',
    '  | { type: "ping" };',
    "",
    "export type DaemonMessage =",
    '  | { type: "hello_ok"; protocol_major: number; learner_name: string; talk_mode: string; voice: string }',
    '  | { type: "transcript"; turn_id: string;',
    '      role: "child" | "tutor"; text: string; partial: boolean }',
    '  | { type: "board"; turn_id: string; elements: BoardElement[] }',
    '  | { type: "choices"; turn_id: string; prompt: string;',
    "      options: { id: string; label: string }[] }",
    '  | { type: "audio_chunk"; turn_id: string; seq: number;',
    "      pcm_b64: string; sample_rate: number }",
    '  | { type: "video"; action: "play" | "pause" | "resume"',
    '      | "seek" | "stop" | "destroy"; video_id: string;',
    "      start_s: number | null; end_s: number | null; at_s: number | null }",
    '  | { type: "state"; name: "home" | "listening" | "thinking"',
    '      | "speaking" | "board" | "video" | "app" | "offline"',
    '      | "parent_unlock" | "parent_menu"; detail: string }',
    '  | { type: "recap"; text: string }',
    '  | { type: "error"; message: string }',
    '  | { type: "pong" };',
    "",
]


def render_typescript() -> str:
    return "\n".join(_LINES)
