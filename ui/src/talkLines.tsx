// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

export type TalkPair = { child: string; tutor: string };

export function nextTalkPair(current: TalkPair, role: string, text: string): TalkPair {
  if (role === "child") return { child: text, tutor: "" };
  if (role === "tutor") return { child: current.child, tutor: text };
  return current;
}

export function speakerInitial(name: string): string {
  const trimmed = name.trim();
  return trimmed ? trimmed[0]!.toUpperCase() : "?";
}

export function talkWords(text: string): string[] {
  return text.split(/\s+/).filter(Boolean);
}

export function spokenWordIndex(text: string, elapsedMs: number, durationMs: number): number {
  const words = talkWords(text);
  if (words.length === 0 || durationMs <= 0) return -1;
  const weights = words.map((word) => Math.max(word.replace(/\W/g, "").length, 1));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  const target = Math.min(Math.max(elapsedMs / durationMs, 0), 0.999) * total;
  let seen = 0;
  for (let index = 0; index < words.length; index += 1) {
    seen += weights[index] ?? 1;
    if (target < seen) return index;
  }
  return words.length - 1;
}

export function TalkLines({
  name,
  child,
  tutor,
  spokenIndex = -1,
  overVideo = false,
}: {
  name: string;
  child: string;
  tutor: string;
  spokenIndex?: number;
  overVideo?: boolean;
}) {
  if (!child && !tutor) return null;
  return (
    <section className={overVideo ? "talk-lines on-video" : "talk-lines"} aria-label="what we said">
      {child ? (
        <p className="talk-line child">
          <span className="talk-icon child" aria-hidden="true">
            {speakerInitial(name)}
          </span>
          <span>{child}</span>
        </p>
      ) : null}
      {tutor ? (
        <p className="talk-line tutor">
          <span className="talk-icon tutor" aria-hidden="true">
            S
          </span>
          <span>
            {talkWords(tutor).map((word, index) => (
              <span key={`${word}-${index}`} className={index === spokenIndex ? "spoken-now" : undefined}>
                {index > 0 ? " " : ""}
                {word}
              </span>
            ))}
          </span>
        </p>
      ) : null}
    </section>
  );
}
