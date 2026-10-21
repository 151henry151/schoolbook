# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""OpenAI image generation. Bytes are saved locally before the child sees them."""

from __future__ import annotations

import base64

import httpx


class OpenAIImages:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(base_url="https://api.openai.com", timeout=90)

    def generate(self, prompt: str) -> bytes:
        last: httpx.Response | None = None
        for model, extra in (
            ("gpt-image-1", {}),
            ("dall-e-3", {"response_format": "b64_json"}),
        ):
            last = self._client.post(
                "/v1/images/generations",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": model, "prompt": prompt, "size": "1024x1024", "n": 1, **extra},
            )
            if last.status_code >= 400:
                continue
            data = last.json().get("data", [{}])[0]
            if not isinstance(data, dict):
                continue
            encoded = data.get("b64_json")
            if isinstance(encoded, str) and encoded:
                return base64.b64decode(encoded)
            url = data.get("url")
            if isinstance(url, str) and url:
                downloaded = self._client.get(url)
                downloaded.raise_for_status()
                return downloaded.content
        if last is not None:
            last.raise_for_status()
        raise RuntimeError("image generation returned no image")
