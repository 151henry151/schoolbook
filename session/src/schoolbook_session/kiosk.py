# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Launch Chromium inside cage and leave when the parent ends the session."""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from schoolbook_session.agent import BROWSER_RESTART_S, chromium_kiosk_argv

END_FILE = "kiosk.end"
CHROMIUM_NAMES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")


class KioskError(RuntimeError):
    pass


class BrowserProc(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


Spawn = Callable[[list[str]], BrowserProc]
Sleeper = Callable[[float], None]


def cage_argv(inner: list[str], cage: str = "cage") -> list[str]:
    """Cage without `-s`, so VT switching stays off."""
    return [cage, "--", *inner]


def require_binary(name: str, resolver: Callable[[str], str | None] | None = None) -> str:
    found = (resolver or shutil.which)(name)
    if not found:
        raise KioskError(f"{name} is not installed")
    return found


def find_chromium(resolver: Callable[[str], str | None] | None = None) -> str:
    lookup = resolver or shutil.which
    for name in CHROMIUM_NAMES:
        found = lookup(name)
        if found:
            return found
    raise KioskError("chromium is not installed")


def request_end(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / END_FILE).write_text("end\n", encoding="utf-8")


def end_requested(data_dir: Path) -> bool:
    return (data_dir / END_FILE).is_file()


def clear_end(data_dir: Path) -> None:
    path = data_dir / END_FILE
    if path.is_file():
        path.unlink()


def run_chromium_kiosk(
    url: str,
    data_dir: Path,
    *,
    spawn: Spawn | None = None,
    sleep: Sleeper | None = None,
    chromium: str = "chromium",
) -> None:
    clear_end(data_dir)
    launcher = spawn or _spawn
    nap = sleep or time.sleep
    while True:
        # A saved Chromium cache can otherwise load an old UI after an upgrade,
        # including before that UI ever receives our new cache-control headers.
        parts = urlsplit(url)
        query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                 if key != "_schoolbook_start"]
        query.append(("_schoolbook_start", uuid.uuid4().hex))
        fresh_url = urlunsplit(parts._replace(query=urlencode(query)))
        argv = chromium_kiosk_argv(fresh_url, chromium)
        browser = launcher(argv)
        while browser.poll() is None:
            if end_requested(data_dir):
                browser.terminate()
                browser.wait(timeout=5)
                return
            nap(0.2)
        if end_requested(data_dir):
            return
        nap(BROWSER_RESTART_S)


def _spawn(argv: list[str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
