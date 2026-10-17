# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from datetime import UTC, datetime, timedelta

from schoolbookd.learner.memory import (
    ProfileInput,
    assemble_profile,
    decay_interest,
    mention_interest,
    next_stretch,
)
from schoolbookd.learner.rules import SkillSnapshot, apply_outcome, mark_review_due


def test_practicing_becomes_secure_after_enough_evidence_on_two_days() -> None:
    when = datetime(2026, 10, 7, tzinfo=UTC)
    current = SkillSnapshot(state="practicing", mastery=0.9, evidence_count=4, distinct_days=1)
    updated, review = apply_outcome(current, "correct", when=when, distinct_days_after=2)
    assert updated.state == "secure"
    assert review == when + timedelta(days=2)


def test_secure_review_intervals_grow() -> None:
    when = datetime(2026, 10, 7, tzinfo=UTC)
    current = SkillSnapshot(state="secure", mastery=0.9, evidence_count=6, distinct_days=3)
    updated, review = apply_outcome(current, "correct", when=when, distinct_days_after=3)
    assert review == when + timedelta(days=7)
    again, later = apply_outcome(updated, "correct", when=when, distinct_days_after=3)
    assert later == when + timedelta(days=21)
    assert again.review_stage == 2


def test_low_mastery_does_not_secure() -> None:
    when = datetime(2026, 10, 7, tzinfo=UTC)
    current = SkillSnapshot(state="practicing", mastery=0.2, evidence_count=8, distinct_days=4)
    updated, review = apply_outcome(current, "not_yet", when=when, distinct_days_after=4)
    assert updated.state == "practicing"
    assert review is None


def test_observed_evidence_moves_mastery_less_than_a_direct_check() -> None:
    when = datetime(2026, 10, 7, tzinfo=UTC)
    start = SkillSnapshot(state="practicing", mastery=0.4, evidence_count=2, distinct_days=1)
    direct, _ = apply_outcome(start, "correct", when=when, distinct_days_after=1)
    observed, _ = apply_outcome(start, "correct", when=when, distinct_days_after=1, observed=True)
    assert direct.mastery > observed.mastery


def test_review_due_flag() -> None:
    now = datetime(2026, 10, 7, tzinfo=UTC)
    current = SkillSnapshot(state="secure", mastery=0.9, evidence_count=6, distinct_days=2)
    due = mark_review_due(current, now=now, next_review_at=now - timedelta(days=1))
    assert due.review_due


def test_interest_decays_and_rises_on_mention() -> None:
    start = datetime(2026, 9, 1, tzinfo=UTC)
    later = start + timedelta(days=21)
    assert decay_interest(1.0, start, later) == 0.5
    assert mention_interest(0.5, later, later) == 0.7


def test_stretch_moves_one_step() -> None:
    assert next_stretch(4, "easy") == 5
    assert next_stretch(4, "lost") == 3
    assert next_stretch(4, "ok") == 4
    assert next_stretch(10, "easy") == 10


def test_profile_snapshot() -> None:
    text = assemble_profile(
        ProfileInput(
            name="Sam",
            age=6,
            house_notes=["we're vegetarian"],
            interests=[("sharks", 0.8), ("trains", 0.4)],
            practicing=["math.counting.to20"],
            review_due=["reading.phonics.cvc_words"],
            tutor_notes=["Wants to finish the volcano story"],
            stretch={"science": 3},
        )
    )
    assert "Name: Sam. Age: 6." in text
    assert "we're vegetarian" in text
    assert "sharks" in text
    assert "math.counting.to20" in text
    assert "volcano story" in text
    assert "science 3" in text
