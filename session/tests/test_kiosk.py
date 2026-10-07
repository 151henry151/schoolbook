# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

import pytest

from schoolbook_session.kiosk import (
    KioskError,
    cage_argv,
    end_requested,
    request_end,
    require_binary,
    run_chromium_kiosk,
)


def test_cage_argv_runs_the_session_without_vt_switching() -> None:
    argv = cage_argv(["schoolbook-session", "kiosk", "--url", "http://127.0.0.1:8765/"])
    assert argv[0] == "cage"
    assert argv[1] == "--"
    assert "-s" not in argv
    assert argv[-1] == "http://127.0.0.1:8765/"


def test_require_binary_names_the_missing_tool() -> None:
    with pytest.raises(KioskError, match="cage"):
        require_binary("cage", resolver=lambda _name: None)


def test_end_flag_roundtrip(tmp_path: Path) -> None:
    assert end_requested(tmp_path) is False
    request_end(tmp_path)
    assert end_requested(tmp_path) is True


def test_chromium_kiosk_exits_when_the_parent_ends_the_session(tmp_path: Path) -> None:
    started: list[list[str]] = []

    class FakeBrowser:
        def __init__(self) -> None:
            self.pid = 42
            self.ended = False

        def poll(self) -> int | None:
            return 0 if self.ended else None

        def terminate(self) -> None:
            self.ended = True

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 0

    browser = FakeBrowser()

    def spawn(argv: list[str]) -> FakeBrowser:
        started.append(argv)
        return browser

    def sleep(_seconds: float) -> None:
        request_end(tmp_path)

    run_chromium_kiosk("http://127.0.0.1:8765/", tmp_path, spawn=spawn, sleep=sleep, chromium="chromium")
    assert started
    assert "--kiosk" in started[0]
    assert started[0][-1] == "http://127.0.0.1:8765/"
    assert browser.ended is True


def test_chromium_kiosk_restarts_after_a_crash(tmp_path: Path) -> None:
    class FakeBrowser:
        def __init__(self, code: int | None) -> None:
            self.code = code
            self.ended = False
            self.pid = 7

        def poll(self) -> int | None:
            if self.ended:
                return 0
            return self.code

        def terminate(self) -> None:
            self.ended = True

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 0

    browsers = [FakeBrowser(1), FakeBrowser(None)]
    spawned = 0

    def spawn(argv: list[str]) -> FakeBrowser:
        nonlocal spawned
        del argv
        browser = browsers[spawned]
        spawned += 1
        return browser

    def sleep(_seconds: float) -> None:
        if spawned >= 2:
            request_end(tmp_path)

    run_chromium_kiosk("http://127.0.0.1:8765/", tmp_path, spawn=spawn, sleep=sleep, chromium="chromium")
    assert spawned == 2
    assert browsers[1].ended is True
