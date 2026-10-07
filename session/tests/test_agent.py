# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import json

import pytest

from schoolbook_protocol.messages import LaunchApp
from schoolbook_session.agent import (
    LaunchDenied,
    accept_launch,
    chromium_kiosk_argv,
    handle_line,
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
    assert "-s" not in argv
    with pytest.raises(LaunchDenied):
        chromium_kiosk_argv("https://example.com")


def test_handle_line_reports_app_started() -> None:
    result = handle_line(
        json.dumps({"type": "launch", "app_id": "gcompris", "argv": ["gcompris-qt", "-f"]}),
        {"gcompris-qt"},
    )
    assert result["type"] == "app_started"


def test_xdg_open_stub_does_nothing() -> None:
    assert xdg_open_stub(["xdg-open", "https://example.com"]) == 0
