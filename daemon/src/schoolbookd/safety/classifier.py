# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Optional post-turn review. It flags; it does not block speech that already passed the local check."""

from __future__ import annotations


class KeywordClassifier:
    def review(self, text: str) -> str | None:
        lowered = text.lower()
        if "http://" in lowered or "https://" in lowered:
            return "link in tutor speech"
        return None
