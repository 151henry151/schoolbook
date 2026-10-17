# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Local espeak-ng TTS. WAV on stdout is unpacked to PCM for the child UI."""

from __future__ import annotations

import io
import shutil
import subprocess
import wave


def espeak_command(text: str, voice: str = "en-us") -> list[str]:
    del text
    return ["espeak-ng", "-v", voice, "-s", "140", "--stdout"]


def wav_pcm(blob: bytes) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(blob), "rb") as handle:
        return handle.readframes(handle.getnframes()), handle.getframerate()


class EspeakTTS:
    sample_rate: int = 22050

    def __init__(self, binary: str = "espeak-ng", voice: str = "en-us") -> None:
        self.binary = binary
        self.voice = voice

    def synthesize(self, text: str) -> bytes:
        if shutil.which(self.binary) is None:
            raise RuntimeError("espeak-ng is not installed; set providers.tts to fake for development")
        completed = subprocess.run(
            espeak_command(text, self.voice),
            input=text.encode(),
            capture_output=True,
            check=True,
        )
        pcm, rate = wav_pcm(completed.stdout)
        self.sample_rate = rate
        return pcm
