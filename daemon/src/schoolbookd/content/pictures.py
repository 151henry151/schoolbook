# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Make a local picture for the child. The tutor never puts a web URL on the board."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000100ffff03000006000557bf0000000049"
    "454e44ae426082"
)


def picture_prompt(brief: str) -> str:
    return (
        "Draw one clear educational illustration as a complete SVG "
        "for a curious six-year-old. "
        "The tutor's point to illustrate is: "
        f"{brief} "
        "Choose the best way to show that point: how it looks, how it works, "
        "a simple process, or a size comparison if that is the point. "
        "Use your judgment. Do not only make scale charts. "
        "If you do compare size, depth, or distance, make everyday objects "
        "big and visible. Stack copies if one thing is huge. "
        "Do not use a ruler, tick marks, or tiny true-scale dots. "
        "No zoom boxes. "
        "Make the idea obvious, not an artistic scene. "
        "No text, letters, logos, or watermark. "
        "Not a baby cartoon or nursery drawing. "
        "Return only the SVG."
    )


def picture_id(topic: str, brief: str = "") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    base = slug[:40].strip("-") or "picture"
    if brief.strip() and brief.strip() != topic.strip():
        digest = hashlib.sha256(brief.encode()).hexdigest()[:8]
        return f"{base[:31].strip('-')}-{digest}"
    return base


class PictureMaker(Protocol):
    def generate(self, prompt: str) -> bytes: ...


class FakePictures:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> bytes:
        self.prompts.append(prompt)
        return TINY_PNG


def picture_suffix(data: bytes) -> str:
    raw = data.lstrip()
    if raw.startswith(b"<svg") or raw.startswith(b"<?xml"):
        return ".svg"
    return ".png"
