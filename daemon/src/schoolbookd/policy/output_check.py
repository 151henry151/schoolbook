# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Local word and pattern check applied before text-to-speech."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REDIRECT = "Let's talk about something else. What are you wondering about?"

_DISTRESS = re.compile(
    r"\b("
    r"hurt me|hurting me|hits me|hit me|scared|afraid|sad|nobody likes me|"
    r"don't tell|do not tell|secret from"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class OutputHit:
    pattern: str
    replacement: str


class OutputCheck:
    def __init__(self, patterns: list[re.Pattern[str]]) -> None:
        self._patterns = patterns

    @classmethod
    def load(cls, path: Path) -> OutputCheck:
        patterns: list[re.Pattern[str]] = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("re:"):
                    patterns.append(re.compile(stripped[3:], re.IGNORECASE))
                else:
                    patterns.append(re.compile(rf"\b{re.escape(stripped)}\b", re.IGNORECASE))
        return cls(patterns)

    def inspect(self, sentence: str) -> OutputHit | None:
        for pattern in self._patterns:
            if pattern.search(sentence):
                return OutputHit(pattern.pattern, REDIRECT)
        return None


def looks_like_distress(text: str) -> bool:
    return _DISTRESS.search(text) is not None
