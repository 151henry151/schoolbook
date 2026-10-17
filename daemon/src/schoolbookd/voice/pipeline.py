# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Tap-to-talk audio, interruption, and sentence-sized TTS chunks."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from schoolbookd.providers.base import STTProvider, TTSProvider

SAMPLE_RATE = 16000
SILENCE_END_S = 1.5


@dataclass
class ListenBuffer:
    pcm: bytearray = field(default_factory=bytearray)


def append_pcm(buffer: ListenBuffer, pcm_b64: str) -> None:
    if not pcm_b64:
        return
    buffer.pcm.extend(base64.b64decode(pcm_b64))


def transcribe_buffer(
    stt: STTProvider, buffer: ListenBuffer, hints: list[str] | None = None
) -> tuple[str, float]:
    if not buffer.pcm:
        return "", 0.0
    return stt.transcribe(bytes(buffer.pcm), hints=hints)


def sentence_audio(tts: TTSProvider, sentences: list[str]) -> list[bytes]:
    return [tts.synthesize(sentence) for sentence in sentences if sentence.strip()]


def encode_audio(pcm: bytes) -> str:
    return base64.b64encode(pcm).decode("ascii")


def voice_active(pcm: bytes, threshold: int = 400) -> bool:
    if len(pcm) < 2:
        return False
    peak = 0
    for index in range(0, len(pcm) - 1, 2):
        sample = int.from_bytes(pcm[index : index + 2], "little", signed=True)
        peak = max(peak, abs(sample))
    return peak >= threshold


def silence_ends_turn(silent_s: float) -> bool:
    return silent_s >= SILENCE_END_S
