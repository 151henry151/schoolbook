# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Provider interfaces. Tests use the fakes; cloud clients stay behind these."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SystemBlock:
    text: str
    cache: bool


@dataclass
class ToolUse:
    name: str
    arguments: dict[str, object]
    call_id: str = "call"


@dataclass
class LLMRequest:
    model: str
    system: list[SystemBlock]
    messages: list[dict[str, object]]
    tools: list[dict[str, object]] = field(default_factory=list)


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolUse] = field(default_factory=list)


class LLMProvider(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse: ...


class STTProvider(Protocol):
    def transcribe(self, pcm: bytes, *, hints: list[str] | None = None) -> tuple[str, float]: ...


class TTSProvider(Protocol):
    def synthesize(self, text: str) -> bytes: ...


@dataclass
class FakeLLM:
    script: list[LLMResponse]
    requests: list[LLMRequest] = field(default_factory=list)

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self.script:
            return LLMResponse(text="What should we try next?")
        return self.script.pop(0)


@dataclass
class FakeSTT:
    transcripts: list[str]

    def transcribe(self, pcm: bytes, *, hints: list[str] | None = None) -> tuple[str, float]:
        del pcm, hints
        if not self.transcripts:
            return "", 0.0
        return self.transcripts.pop(0), 0.95


@dataclass
class FakeTTS:
    sample_rate: int = 16000

    def synthesize(self, text: str) -> bytes:
        words = max(len(text.split()), 1)
        samples = self.sample_rate * words // 10
        return b"\x00\x00" * samples
