# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Claude draws educational scale diagrams as SVG from the tutor's brief."""

from __future__ import annotations

import re

import httpx

_SVG = re.compile(r"<svg\b[\s\S]*?</svg>", re.I)


def extract_svg(text: str) -> str:
    match = _SVG.search(text or "")
    if not match:
        raise RuntimeError("Claude returned no SVG diagram")
    return match.group(0)


class ClaudePictures:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5-5",
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(base_url="https://api.anthropic.com", timeout=90)

    def generate(self, prompt: str) -> bytes:
        response = self._client.post(
            "/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "max_tokens": 8000,
                "system": (
                    "You draw educational SVG illustrations for a six-year-old. "
                    "The user message is the point to show. "
                    "Choose the best picture to make that point clear. "
                    "Use your judgment. "
                    "If the point is size, depth, or distance, everyday objects "
                    "must be large and visible; stack copies if needed. "
                    "No ruler, tiny specks, zoom boxes, words, or letters. "
                    "Return only SVG."
                ),
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        text = ""
        for block in response.json().get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text += str(block.get("text", ""))
        return extract_svg(text).encode()
