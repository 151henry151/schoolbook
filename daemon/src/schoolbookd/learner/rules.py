# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Skill-state transitions. Practicing becomes secure only with enough varied evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

OUTCOME_SCORES = {"correct": 1.0, "with_help": 0.5, "not_yet": 0.0}
REVIEW_INTERVALS = (
    timedelta(days=2),
    timedelta(days=7),
    timedelta(days=21),
)
MASTERY_ALPHA = 0.35
OBSERVER_WEIGHT = 0.5


@dataclass(frozen=True)
class SkillSnapshot:
    state: str = "not_seen"
    mastery: float = 0.0
    evidence_count: int = 0
    distinct_days: int = 0
    review_stage: int = 0
    review_due: bool = False


def apply_outcome(
    current: SkillSnapshot,
    outcome: str,
    *,
    when: datetime,
    distinct_days_after: int,
    observed: bool = False,
) -> tuple[SkillSnapshot, datetime | None]:
    score = OUTCOME_SCORES[outcome]
    weight = OBSERVER_WEIGHT if observed else 1.0
    mastery = (1 - MASTERY_ALPHA * weight) * current.mastery + (MASTERY_ALPHA * weight) * score
    evidence = current.evidence_count + 1
    state = _next_state(current.state, mastery, evidence, distinct_days_after)
    stage = current.review_stage
    next_review: datetime | None = None
    if state == "secure":
        if current.state != "secure":
            stage = 0
        elif outcome == "correct":
            stage = min(stage + 1, len(REVIEW_INTERVALS) - 1)
        next_review = when + REVIEW_INTERVALS[stage]
    return (
        SkillSnapshot(
            state=state,
            mastery=mastery,
            evidence_count=evidence,
            distinct_days=distinct_days_after,
            review_stage=stage,
            review_due=False,
        ),
        next_review,
    )


def _next_state(state: str, mastery: float, evidence: int, distinct_days: int) -> str:
    if state == "not_seen":
        return "introduced"
    if state == "introduced":
        return "practicing"
    enough = mastery >= 0.8 and evidence >= 5 and distinct_days >= 2
    if state in {"practicing", "secure"} and enough:
        return "secure"
    if state == "secure":
        return "practicing" if mastery < 0.8 else "secure"
    return "practicing"


def mark_review_due(
    current: SkillSnapshot,
    *,
    now: datetime,
    next_review_at: datetime | None,
) -> SkillSnapshot:
    due = current.state == "secure" and next_review_at is not None and now >= next_review_at
    return SkillSnapshot(
        state=current.state,
        mastery=current.mastery,
        evidence_count=current.evidence_count,
        distinct_days=current.distinct_days,
        review_stage=current.review_stage,
        review_due=due,
    )
