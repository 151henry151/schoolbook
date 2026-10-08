# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Resolve a YouTube song to a local audio stream. The child UI never loads a music video."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from typing import Any

import httpx

_ID = re.compile(r"^[A-Za-z0-9_-]+$")
AUDIO_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}


def song_src(video_id: str) -> str:
    if not video_id or not _ID.fullmatch(video_id):
        raise ValueError("video id must stay a YouTube id")
    return f"/songs/{video_id}"


def resolve_audio_url(
    video_id: str,
    *,
    run: Callable[..., Any] = subprocess.run,
) -> str:
    song_src(video_id)
    result = run(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "-f",
            "bestaudio[ext=m4a]/bestaudio/best",
            "-g",
            "--",
            video_id,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    lines = [
        line.strip()
        for line in (result.stdout or "").splitlines()
        if line.strip().startswith("http")
    ]
    if int(getattr(result, "returncode", 1)) != 0 or not lines:
        raise RuntimeError("could not resolve song audio")
    return lines[-1]


def load_song_audio(video_id: str, *, run: Callable[..., Any] = subprocess.run) -> tuple[bytes, str]:
    url = resolve_audio_url(video_id, run=run)
    response = httpx.get(url, headers=AUDIO_HEADERS, follow_redirects=True, timeout=60)
    response.raise_for_status()
    media = (response.headers.get("content-type") or "audio/mp4").split(";", 1)[0] or "audio/mp4"
    return response.content, media
