# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Claude Messages API client. The first three system blocks are cacheable."""

from __future__ import annotations

import json

import httpx

from schoolbookd.providers.base import LLMRequest, LLMResponse, ToolUse


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(base_url="https://api.anthropic.com", timeout=30)

    def complete(self, request: LLMRequest) -> LLMResponse:
        system = [
            {
                "type": "text",
                "text": block.text,
                **({"cache_control": {"type": "ephemeral"}} if block.cache else {}),
            }
            for block in request.system
        ]
        response = self._client.post(
            "/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": request.model or self._model,
                "max_tokens": 400,
                "system": system,
                "messages": request.messages,
            },
        )
        response.raise_for_status()
        payload = response.json()
        text = ""
        calls: list[ToolUse] = []
        for block in payload.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
            elif block.get("type") == "tool_use":
                calls.append(ToolUse(block["name"], dict(block.get("input", {})), block.get("id", "call")))
        return LLMResponse(text=text, tool_calls=calls)


def cache_header_present(body: dict[str, object]) -> bool:
    system = body.get("system")
    if not isinstance(system, list) or not system:
        return False
    first = system[0]
    return isinstance(first, dict) and "cache_control" in first and "cache_control" not in system[-1]


def dump_example(request: LLMRequest) -> str:
    return json.dumps({"model": request.model})
