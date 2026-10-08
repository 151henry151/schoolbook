# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Make a local picture for the child. The tutor never puts a web URL on the board."""

from __future__ import annotations

import re
from typing import Protocol

TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000100ffff03000006000557bf0000000049"
    "454e44ae426082"
)


def picture_prompt(topic: str) -> str:
    return (
        f"A clear, friendly educational illustration of {topic} for a curious six-year-old. "
        "Show what it really looks like. No text, letters, logos, or watermark. "
        "Not a baby cartoon or nursery drawing."
    )


def picture_id(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    return (slug[:40].strip("-") or "picture")


class PictureMaker(Protocol):
    def generate(self, prompt: str) -> bytes: ...


class FakePictures:
    def generate(self, prompt: str) -> bytes:
        del prompt
        return TINY_PNG
