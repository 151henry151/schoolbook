# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import json
from pathlib import Path

import pytest

from schoolbook_protocol.messages import LaunchApp
from schoolbook_session.agent import (
    BROWSER_RESTART_S,
    LaunchDenied,
    accept_launch,
    chromium_kiosk_argv,
    handle_line,
    serve_socket,
    supervise_browser,
    xdg_open_stub,
)


def test_launch_rejects_commands_outside_the_allowlist() -> None:
    message = LaunchApp(app_id="shell", argv=["bash", "-c", "id"])
    with pytest.raises(LaunchDenied):
        accept_launch(message, {"gcompris-qt"})


def test_launch_keeps_the_daemon_argv() -> None:
    message = LaunchApp(
        app_id="gcompris",
        argv=["gcompris-qt", "--enable-kioskmode", "--launch", "enumerate"],
    )
    assert accept_launch(message, {"gcompris-qt"}) == message.argv


def test_chromium_stays_on_localhost() -> None:
    argv = chromium_kiosk_argv("http://127.0.0.1:8765/")
    assert "--kiosk" in argv
    assert "--use-fake-ui-for-media-stream" in argv
    assert "-s" not in argv
    with pytest.raises(LaunchDenied):
        chromium_kiosk_argv("https://example.com")


def test_handle_line_reports_app_started() -> None:
    result = handle_line(
        json.dumps({"type": "launch", "app_id": "gcompris", "argv": ["gcompris-qt", "-f"]}),
        {"gcompris-qt"},
    )
    assert result["type"] == "app_started"


def test_xdg_open_stub_does_nothing(tmp_path: Path) -> None:
    log = tmp_path / "xdg.log"
    assert xdg_open_stub(["xdg-open", "https://example.com"], log) == 0
    assert "example.com" in log.read_text(encoding="utf-8")


def test_crashed_browser_restarts_after_two_seconds() -> None:
    sleeps: list[float] = []
    restarts = supervise_browser(lambda: object(), lambda _handle: 1, sleeps.append, limit=2)
    assert restarts == 2
    assert sleeps == [BROWSER_RESTART_S]


def test_unix_socket_launches_only_allowlisted_argv(tmp_path: Path) -> None:
    import socket
    import threading

    path = tmp_path / "schoolbook.sock"
    ready = threading.Event()
    thread = threading.Thread(
        target=serve_socket,
        args=(path, {"gcompris-qt"}, ready.set),
        daemon=True,
    )
    thread.start()
    assert ready.wait(2)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(path))
    payload = {"type": "launch", "app_id": "gcompris", "argv": ["gcompris-qt", "-f"]}
    client.sendall((json.dumps(payload) + "\n").encode())
    data = b""
    while b"\n" not in data:
        data += client.recv(4096)
    assert json.loads(data.decode())["type"] == "app_started"
    client.close()
    thread.join(2)
