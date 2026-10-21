# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Interests, video stretch, and the session-start profile."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


def decay_interest(strength: float, last_mentioned: datetime, now: datetime) -> float:
    days = max((now - last_mentioned).total_seconds(), 0) / 86400
    decayed = strength * (0.5 ** (days / 21))
    return float(decayed)


def mention_interest(strength: float, last_mentioned: datetime, now: datetime) -> float:
    return min(1.0, decay_interest(strength, last_mentioned, now) + 0.2)


def next_stretch(current: int, outcome: str) -> int:
    if outcome == "easy":
        return min(10, current + 1)
    if outcome == "lost":
        return max(1, current - 1)
    return current


@dataclass(frozen=True)
class ProfileInput:
    name: str
    age: int
    house_notes: list[str]
    interests: list[tuple[str, float]]
    practicing: list[str]
    review_due: list[str]
    tutor_notes: list[str]
    stretch: dict[str, int]


def assemble_profile(data: ProfileInput, *, char_budget: int = 6000) -> str:
    interests = ", ".join(topic for topic, _strength in data.interests[:5]) or "none yet"
    practicing = ", ".join(data.practicing[:10]) or "none"
    due = ", ".join(data.review_due[:10]) or "none"
    notes = data.tutor_notes[:3]
    house = data.house_notes
    stretch = ", ".join(f"{subject} {level}" for subject, level in sorted(data.stretch.items()))
    lines = [
        f"Name: {data.name}. Age: {data.age}.",
        f"House notes: {'; '.join(house) if house else 'none'}.",
        f"Interests: {interests}.",
        f"Practicing: {practicing}.",
        f"Due for review: {due}.",
        f"Video stretch: {stretch or 'unset'}.",
        "Tutor notes:",
        *(f"- {note}" for note in notes),
    ]
    text = "\n".join(lines)
    if len(text) <= char_budget:
        return text
    return text[: char_budget - 1] + "…"


def weeks_between(start: datetime, end: datetime) -> int:
    return max(int((end - start) / timedelta(weeks=1)), 0)
