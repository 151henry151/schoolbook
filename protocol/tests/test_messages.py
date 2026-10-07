# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import pytest
from pydantic import ValidationError

from schoolbook_protocol.board import BigText, Board
from schoolbook_protocol.messages import (
    ChoicePrompt,
    parse_client_message,
    parse_daemon_message,
    parse_session_message,
)
from schoolbook_protocol.typescript import render_typescript
from schoolbook_protocol.version import MAJOR, VERSION


def test_version_is_semver() -> None:
    parts = VERSION.split(".")
    assert parts[0] == str(MAJOR)
    assert len(parts) == 3


def test_client_roundtrip() -> None:
    message = parse_client_message(
        {"type": "dev_text", "turn_id": "t1", "text": "what is a shark?"}
    )
    assert message.type == "dev_text"
    assert message.text == "what is a shark?"


def test_daemon_board_roundtrip() -> None:
    message = parse_daemon_message(
        {
            "type": "board",
            "turn_id": "t1",
            "elements": [{"type": "big_text", "text": "shark", "highlights": [0]}],
        }
    )
    assert message.type == "board"
    assert message.elements[0].type == "big_text"


def test_session_launch_roundtrip() -> None:
    message = parse_session_message(
        {"type": "launch", "app_id": "gcompris", "argv": ["gcompris-qt", "--enable-kioskmode"]}
    )
    assert message.type == "launch"
    assert message.argv[0] == "gcompris-qt"


def test_board_rejects_urls() -> None:
    with pytest.raises(ValidationError):
        BigText(text="see https://example.com")


def test_board_caps_dot_count() -> None:
    with pytest.raises(ValidationError):
        Board.model_validate({"elements": [{"type": "dots", "count": 21}]})


def test_choices_max_four() -> None:
    options = [{"id": str(i), "label": "A"} for i in range(5)]
    with pytest.raises(ValidationError):
        ChoicePrompt(turn_id="t", prompt="Pick", options=options)


def test_letter_tiles_are_single_letters() -> None:
    with pytest.raises(ValidationError):
        Board.model_validate({"elements": [{"type": "letter_tiles", "letters": ["cat"]}]})


def test_unknown_client_type_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_client_message({"type": "browse", "url": "https://example.com"})


def test_typescript_mentions_major() -> None:
    rendered = render_typescript()
    assert f"PROTOCOL_MAJOR = {MAJOR}" in rendered
    assert 'type: "show_board"' not in rendered
    assert "dev_text" in rendered
