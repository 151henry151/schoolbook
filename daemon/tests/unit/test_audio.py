# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import sys

import pytest

from schoolbookd.content.audio import resolve_audio_url, song_src


def test_song_src_stays_on_the_local_daemon() -> None:
    assert song_src("WUHGwST0Oj4") == "/songs/WUHGwST0Oj4"
    with pytest.raises(ValueError):
        song_src("https://evil.example")
    with pytest.raises(ValueError):
        song_src("")


def test_resolve_audio_url_asks_yt_dlp_for_the_stream() -> None:
    def run(argv: list[str], **_kwargs: object) -> object:
        assert argv[:3] == [sys.executable, "-m", "yt_dlp"]
        assert "-g" in argv
        assert argv[-1] == "WUHGwST0Oj4"
        return type(
            "Result",
            (),
            {"returncode": 0, "stdout": "https://googlevideo.test/audio\n", "stderr": ""},
        )()

    assert resolve_audio_url("WUHGwST0Oj4", run=run) == "https://googlevideo.test/audio"


def test_resolve_audio_url_rejects_a_failed_lookup() -> None:
    def run(_argv: list[str], **_kwargs: object) -> object:
        return type("Result", (), {"returncode": 1, "stdout": "", "stderr": "nope"})()

    with pytest.raises(RuntimeError):
        resolve_audio_url("WUHGwST0Oj4", run=run)
