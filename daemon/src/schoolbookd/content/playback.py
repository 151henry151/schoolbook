# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Watch-along pacing. The tutor does not pause a video more often than the age profile allows."""

from __future__ import annotations


def pause_allowed(last_pause_s: float | None, now: float, min_gap_s: float) -> bool:
    if last_pause_s is None:
        return True
    return now - last_pause_s >= min_gap_s


def split_summary(text: str) -> tuple[str, str]:
    import json

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text, ""
    if not isinstance(data, dict):
        return text, ""
    parent = data.get("parent_summary", text)
    notes = data.get("tutor_notes", "")
    return str(parent), str(notes)
