// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

export const PROTOCOL_MAJOR = 1;

export type BoardElement =
  | { type: "big_text"; text: string; highlights?: number[] }
  | { type: "letter_tiles"; letters: string[] }
  | { type: "number"; value: string }
  | { type: "equation"; text: string }
  | { type: "dots"; count: number; emoji?: string }
  | { type: "objects"; count: number; emoji?: string | null; image_id?: string | null }
  | { type: "number_line"; start: number; end: number; marks?: number[]; hops?: { start: number; end: number }[] }
  | { type: "image"; image_id: string }
  | { type: "shapes"; items: { shape: string; color: string }[] };
