# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Split tutor text into short spoken sentences and strip markdown."""

from __future__ import annotations

import re

_MARKDOWN = re.compile(r"[*_`#>\[\]()]+")
_EMOJI = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF]+",
)
_SENTENCE = re.compile(r"[^.!?]+[.!?]?")


def sanitize_speech(text: str) -> str:
    cleaned = _EMOJI.sub("", _MARKDOWN.sub("", text))
    return " ".join(cleaned.split())


def chunk_sentences(text: str, *, max_sentences: int, max_words: int) -> list[str]:
    spoken = sanitize_speech(text)
    if not spoken:
        return []
    pieces = [part.strip() for part in _SENTENCE.findall(spoken) if part.strip()]
    limited: list[str] = []
    for piece in pieces:
        words = piece.split()
        while words:
            take = words[:max_words]
            words = words[max_words:]
            sentence = " ".join(take)
            if sentence[-1] not in ".!?":
                sentence += "."
            limited.append(sentence)
            if len(limited) >= max_sentences:
                return limited
    return limited
