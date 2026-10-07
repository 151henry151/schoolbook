# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""whisper.cpp command builder. Audio stays on the machine when this provider is selected."""

from __future__ import annotations

from pathlib import Path


def whisper_command(wav: Path, model: Path, binary: str = "whisper-cli") -> list[str]:
    return [binary, "-m", str(model), "-f", str(wav), "--no-timestamps", "-otxt"]


class WhisperSTT:
    def transcribe(self, pcm: bytes, *, hints: list[str] | None = None) -> tuple[str, float]:
        del pcm, hints
        raise RuntimeError("whisper.cpp is not bundled; install it or use providers.stt: fake")
