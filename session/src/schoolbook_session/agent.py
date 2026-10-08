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
        "--disable-infobars",
        "--password-store=basic",
        "--autoplay-policy=no-user-gesture-required",
        "--use-fake-ui-for-media-stream",
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


def xdg_open_stub(argv: list[str], log: Path | None = None) -> int:
    """Replacement for xdg-open in the kid account. It logs and does nothing."""
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(" ".join(argv) + "\n")
    return 0


BROWSER_RESTART_S = 2.0


def supervise_browser(
    start: Callable[[], object],
    wait: Callable[[object], int],
    sleep: Callable[[float], None],
    *,
    limit: int = 3,
) -> int:
    """Restart a crashed browser after two seconds. A clean exit stops the loop."""
    restarts = 0
    while True:
        handle = start()
        code = wait(handle)
        if code == 0:
            return restarts
        restarts += 1
        if restarts >= limit:
            return restarts
        sleep(BROWSER_RESTART_S)


def serve_socket(path: Path, allowlist: set[str], ready: Callable[[], None] | None = None) -> None:
    """Accept one connection of newline-delimited session messages."""
    import socket

    if path.exists():
        path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    if ready is not None:
        ready()
    connection, _address = server.accept()
    with connection, server:
        pending = b""
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    result = handle_line(line.decode(), allowlist)
                except Exception as exc:
                    result = {"type": "error", "message": str(exc)}
                connection.sendall((json.dumps(result) + "\n").encode())
