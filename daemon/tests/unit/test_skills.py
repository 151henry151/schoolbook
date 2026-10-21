# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from schoolbookd.content.skills import load_skill_rows


def test_core_skills_include_the_spec_examples() -> None:
    rows = load_skill_rows(Path("skills/core.yaml"))
    ids = {row.id for row in rows}
    assert "math.counting.to20" in ids
    assert "reading.phonics.cvc_words" in ids
    assert "science.living_things.needs" in ids
    assert "cs.sequencing.instructions" in ids
    assert "philosophy.fairness" in ids
    counting = next(row for row in rows if row.id == "math.counting.to20")
    assert counting.parent_id == "math.counting"
