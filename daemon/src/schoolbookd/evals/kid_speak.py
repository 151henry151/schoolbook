# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Score tutor replies against the age-6 speaking limits. Live model runs are opt-in."""

from __future__ import annotations

import re

from schoolbookd.tutor.speech import chunk_sentences

_MARKDOWN = re.compile(r"[*_`#]|^\s*[-*] ", re.MULTILINE)


def score_reply(text: str, *, max_sentences: int = 3, max_words: int = 12) -> dict[str, bool]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    questions = text.count("?")
    return {
        "sentence_count": len(sentences) <= max_sentences,
        "sentence_length": all(len(sentence.split()) <= max_words for sentence in sentences),
        "one_question": questions <= 1,
        "no_markdown": _MARKDOWN.search(text) is None,
    }


def passes(text: str) -> bool:
    return all(score_reply(text).values())


def suite_pass_rate(replies: list[str]) -> float:
    if not replies:
        return 0.0
    return sum(1 for reply in replies if passes(reply)) / len(replies)


def spoken_form(text: str) -> str:
    return " ".join(chunk_sentences(text, max_sentences=3, max_words=12))
