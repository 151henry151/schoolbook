# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Session agent. It only executes argv the daemon built from an allowlist."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from schoolbook_protocol.messages import LaunchApp, parse_session_message


class LaunchDenied(Exception):
    pass


def allowlist_from_argv(commands: list[list[str]]) -> set[str]:
    return {Path(command[0]).name for command in commands if command}


def accept_launch(message: LaunchApp, allowlist: set[str]) -> list[str]:
    executable = Path(message.argv[0]).name
    if executable not in allowlist:
        raise LaunchDenied(f"{executable} is not allowlisted")
    if any("\n" in part or "\x00" in part for part in message.argv):
        raise LaunchDenied("argv contains a control character")
    return list(message.argv)


def chromium_kiosk_argv(url: str, binary: str = "chromium") -> list[str]:
    if not url.startswith("http://127.0.0.1") and not url.startswith("http://localhost"):
        raise LaunchDenied("kiosk URL must stay on localhost")
    return [
        binary,
        "--kiosk",
        "--no-first-run",
        "--disable-translate",
        "--autoplay-policy=no-user-gesture-required",
        url,
    ]


def handle_line(line: str, allowlist: set[str]) -> dict[str, object]:
    message = parse_session_message(json.loads(line))
    if message.type == "launch":
        argv = accept_launch(message, allowlist)
        return {"type": "app_started", "app_id": message.app_id, "pid": 0, "argv": argv}
    if message.type == "focus_home":
        return {"type": "focus_home"}
    if message.type == "set_observer":
        return {"type": "observer", "enabled": message.enabled, "interval_s": message.interval_s}
    return {"type": "ignored", "message": message.type}


def spawn(argv: list[str], runner: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen) -> int:
    if os.environ.get("SCHOOLBOOK_SESSION_DRY_RUN") == "1":
        return 0
    process = runner(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return int(process.pid)


def xdg_open_stub(argv: list[str]) -> int:
    """Replacement for xdg-open in the kid account. It logs and does nothing."""
    del argv
    return 0
