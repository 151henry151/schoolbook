# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Local Piper TTS. The binary is optional; the command is what tests check."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def piper_command(text: str, voice: Path, binary: str = "piper") -> list[str]:
    return [binary, "--model", str(voice), "--output_raw"]


class PiperTTS:
    def __init__(self, voice: Path | None = None, binary: str = "piper") -> None:
        self.voice = voice or Path("/usr/share/schoolbook/voices/en_US-lessac-medium.onnx")
        self.binary = binary

    def synthesize(self, text: str) -> bytes:
        if shutil.which(self.binary) is None or not self.voice.is_file():
            raise RuntimeError("Piper is not installed; set providers.tts to fake for development")
        completed = subprocess.run(
            piper_command(text, self.voice, self.binary),
            input=text.encode(),
            capture_output=True,
            check=True,
        )
        return completed.stdout
