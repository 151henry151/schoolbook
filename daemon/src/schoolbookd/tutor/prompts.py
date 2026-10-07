# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Four prompt layers. The first three are marked cacheable."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from schoolbookd.providers.base import SystemBlock


class AgeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    max_sentences_per_turn: int = 3
    max_words_per_sentence: int = 12
    target_reading_grade: int = 1
    talk_mode_default: str = "tap"
    break_suggestions: str = "gentle"
    video_duration_minutes: list[int] = Field(default_factory=lambda: [1, 30])
    video_stretch_steps: int = 1
    watch_along_pause_min_seconds: int = 120
    observer_frame_interval_s: float = 3
    subject_weights: dict[str, int] = Field(default_factory=dict)
    language: str = "en"


def load_age_profile(path: Path) -> AgeProfile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AgeProfile.model_validate(raw)


def render_age_profile(profile: AgeProfile) -> str:
    weights = ", ".join(f"{name} {weight}" for name, weight in profile.subject_weights.items())
    return "\n".join(
        [
            f"Age profile {profile.id}.",
            f"At most {profile.max_sentences_per_turn} sentences.",
            f"Each sentence under about {profile.max_words_per_sentence} words.",
            "One question at a time, then wait.",
            "Everyday words. No markdown, emoji, or lists in speech.",
            "Hint ladder: re-ask, hint, bigger hint, then do it together.",
            "Praise the specific effort, not a generic good job.",
            f"Reading target around grade {profile.target_reading_grade}.",
            f"Break suggestions: {profile.break_suggestions}. Never a hard stop.",
            f"Subject weights: {weights}.",
        ]
    )


def assemble_prompt(
    core: str,
    age_text: str,
    learner_summary: str,
    session_state: str,
) -> list[SystemBlock]:
    return [
        SystemBlock(core.strip(), True),
        SystemBlock(age_text.strip(), True),
        SystemBlock(learner_summary.strip(), True),
        SystemBlock(session_state.strip(), False),
    ]
