# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Local Whisper STT. Tests inject a runner so CI never downloads a model."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

Runner = Callable[[bytes, list[str] | None], tuple[str, float]]


def whisper_command(wav: Path, model: Path, binary: str = "whisper-cli") -> list[str]:
    return [binary, "-m", str(model), "-f", str(wav), "--no-timestamps", "-otxt"]


def pcm16le_to_float32(pcm: bytes) -> list[float]:
    samples: list[float] = []
    for index in range(0, len(pcm) - 1, 2):
        sample = int.from_bytes(pcm[index : index + 2], "little", signed=True)
        samples.append(sample / 32768.0)
    return samples


class WhisperSTT:
    def __init__(self, runner: Runner | None = None, model_size: str = "tiny.en") -> None:
        self._runner = runner
        self._model_size = model_size
        self._model: Any = None

    def transcribe(self, pcm: bytes, *, hints: list[str] | None = None) -> tuple[str, float]:
        if not pcm:
            return "", 0.0
        if self._runner is not None:
            return self._runner(pcm, hints)
        return self._transcribe_local(pcm, hints)

    def _transcribe_local(self, pcm: bytes, hints: list[str] | None) -> tuple[str, float]:
        try:
            import numpy as np
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("install faster-whisper for providers.stt: whisper") from exc
        if self._model is None:
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        audio = np.array(pcm16le_to_float32(pcm), dtype=np.float32)
        prompt = " ".join(hints or [])
        segments, _info = self._model.transcribe(audio, language="en", initial_prompt=prompt or None)
        text = " ".join(segment.text for segment in segments).strip()
        return text, 0.9
