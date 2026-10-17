// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

export const SILENCE_END_MS = 1500;
export const MIN_VOICE_MS = 250;
export const BLIP_MS = 80;
export const MAX_TURN_MS = 8000;

export type HandsFreeState = {
  phase: "armed" | "capturing" | "waiting";
  turnId: string | null;
  silentMs: number;
  voicedMs: number;
  burstMs: number;
};

export type HandsFreeEvent =
  | { type: "start"; turnId: string }
  | { type: "end"; turnId: string }
  | { type: "interrupt"; turnId: string }
  | { type: "frame"; turnId: string }
  | null;

export function armed(): HandsFreeState {
  return { phase: "armed", turnId: null, silentMs: 0, voicedMs: 0, burstMs: 0 };
}

function ended(turnId: string): { state: HandsFreeState; event: HandsFreeEvent } {
  return {
    state: { phase: "waiting", turnId: null, silentMs: 0, voicedMs: 0, burstMs: 0 },
    event: { type: "end", turnId },
  };
}

export function stepHandsFree(
  state: HandsFreeState,
  sample: { voiced: boolean; dtMs: number; speaking: boolean },
  nextId: () => string,
): { state: HandsFreeState; event: HandsFreeEvent } {
  if (sample.voiced) {
    if (state.phase === "waiting" || (sample.speaking && state.phase !== "capturing")) {
      return { state, event: null };
    }
    if (state.phase === "armed") {
      const turnId = nextId();
      return {
        state: { phase: "capturing", turnId, silentMs: 0, voicedMs: sample.dtMs, burstMs: sample.dtMs },
        event: { type: "start", turnId },
      };
    }
    const voicedMs = state.voicedMs + sample.dtMs;
    if (state.turnId && voicedMs >= MAX_TURN_MS) return ended(state.turnId);
    const burstMs = state.burstMs + sample.dtMs;
    const resetSilence = burstMs >= BLIP_MS || state.silentMs === 0;
    return {
      state: { ...state, silentMs: resetSilence ? 0 : state.silentMs, voicedMs, burstMs },
      event: state.turnId ? { type: "frame", turnId: state.turnId } : null,
    };
  }
  if (state.phase === "capturing") {
    const silentMs = state.silentMs + sample.dtMs;
    if (silentMs >= SILENCE_END_MS && state.voicedMs >= MIN_VOICE_MS && state.turnId) {
      return ended(state.turnId);
    }
    return {
      state: { ...state, silentMs, burstMs: 0 },
      event: state.turnId ? { type: "frame", turnId: state.turnId } : null,
    };
  }
  return { state, event: null };
}

export function armIfWaiting(state: HandsFreeState): HandsFreeState {
  return state.phase === "waiting" ? armed() : state;
}
