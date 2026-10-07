# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import base64
from pathlib import Path

from schoolbookd.backup import restic_backup_command
from schoolbookd.content.playback import pause_allowed, split_summary
from schoolbookd.notify import Notifier, ntfy_target
from schoolbookd.providers.base import FakeSTT, FakeTTS
from schoolbookd.secrets_file import upsert_secrets
from schoolbookd.voice.pipeline import (
    ListenBuffer,
    append_pcm,
    silence_ends_turn,
    transcribe_buffer,
    voice_active,
)


def test_empty_audio_does_not_invent_a_transcript() -> None:
    text, confidence = transcribe_buffer(FakeSTT(["shark"]), ListenBuffer())
    assert text == ""
    assert confidence == 0.0


def test_pcm_round_trip_reaches_stt() -> None:
    pcm = b"\x00\x10" * 8
    buffer = ListenBuffer()
    append_pcm(buffer, base64.b64encode(pcm).decode())
    text, confidence = transcribe_buffer(FakeSTT(["shark"]), buffer, hints=["Sam"])
    assert text == "shark"
    assert confidence == 0.95
    assert voice_active(b"\xff\x7f\x00\x00")
    assert silence_ends_turn(1.5)
    assert FakeTTS().synthesize("Hi there.")


def test_watch_along_pause_gap_and_summary_split() -> None:
    assert pause_allowed(None, 10, 120)
    assert not pause_allowed(10, 20, 120)
    parent, notes = split_summary('{"parent_summary": "Counted sharks.", "tutor_notes": "Try tens."}')
    assert parent == "Counted sharks."
    assert notes == "Try tens."


def test_ntfy_is_optional_and_restic_needs_a_repository(tmp_path: Path) -> None:
    notifier = Notifier()
    assert notifier.send("flag", "sad") is False
    assert ntfy_target("https://ntfy.example", "school") == "https://ntfy.example/school"
    command = restic_backup_command("sftp:user@host:/backups", [tmp_path])
    assert command[:4] == ["restic", "-r", "sftp:user@host:/backups", "backup"]
    secrets = tmp_path / "secrets.env"
    upsert_secrets(secrets, {"ANTHROPIC_API_KEY": "secret-value"})
    assert "secret-value" in secrets.read_text(encoding="utf-8")
    assert secrets.stat().st_mode & 0o777 == 0o600
