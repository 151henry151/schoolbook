# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Shared WebSocket and session-agent message models."""

from schoolbook_protocol.board import BoardElement
from schoolbook_protocol.messages import (
    ClientMessage,
    DaemonMessage,
    SessionMessage,
    parse_client_message,
    parse_daemon_message,
    parse_session_message,
)
from schoolbook_protocol.version import MAJOR, MINOR, PATCH, VERSION

__all__ = [
    "MAJOR",
    "MINOR",
    "PATCH",
    "VERSION",
    "BoardElement",
    "ClientMessage",
    "DaemonMessage",
    "SessionMessage",
    "parse_client_message",
    "parse_daemon_message",
    "parse_session_message",
]
