# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Perceptual hash and the screen-observer schedule."""

from __future__ import annotations

from dataclasses import dataclass, field


def average_hash(gray: bytes, width: int, height: int) -> int:
    if width < 1 or height < 1 or len(gray) != width * height:
        raise ValueError("gray buffer does not match width and height")
    bits = 0
    total = 0
    samples: list[int] = []
    for row in range(8):
        for col in range(8):
            x = min(width - 1, int((col + 0.5) * width / 8))
            y = min(height - 1, int((row + 0.5) * height / 8))
            value = gray[y * width + x]
            samples.append(value)
            total += value
    average = total / 64
    for index, value in enumerate(samples):
        if value >= average:
            bits |= 1 << index
    return bits


def hash_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


@dataclass
class ObserverNote:
    text: str
    stuck: bool = False
    progress: str = ""


@dataclass
class ScreenObserver:
    interval_s: float = 3
    analyze_every_s: float = 30
    change_threshold: int = 6
    last_hash: int | None = None
    last_sample_at: float = -999
    last_analysis_at: float = -999
    pending: list[int] = field(default_factory=list)
    notes: list[ObserverNote] = field(default_factory=list)

    def consider(self, gray: bytes, width: int, height: int, now: float) -> bool:
        if now - self.last_sample_at < self.interval_s:
            return False
        digest = average_hash(gray, width, height)
        self.last_sample_at = now
        unchanged = (
            self.last_hash is not None and hash_distance(digest, self.last_hash) <= self.change_threshold
        )
        if unchanged:
            return False
        self.last_hash = digest
        self.pending.append(digest)
        return True

    def analysis_due(self, now: float) -> bool:
        if not self.pending:
            return False
        big_change = len(self.pending) >= 3
        return big_change or now - self.last_analysis_at >= self.analyze_every_s

    def take_pending(self, now: float) -> list[int]:
        frames = self.pending
        self.pending = []
        self.last_analysis_at = now
        return frames

    def unchanged_and_wrong(self, wrong_streak_s: float) -> bool:
        return wrong_streak_s >= 60 and not self.pending
