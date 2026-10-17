// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

/** Count only quiet microphone time when the tutor is ready for a new turn. */
export class IdleListening {
  private quietMs = 0;
  constructor(private readonly timeoutMs = 10_000) {}

  reset() { this.quietMs = 0; }

  frame(dtMs: number, speech: boolean, busy: boolean): boolean {
    if (speech || busy) { this.reset(); return false; }
    if (Number.isFinite(dtMs) && dtMs > 0) this.quietMs += dtMs;
    return this.quietMs >= this.timeoutMs;
  }
}
