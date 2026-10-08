# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from datetime import UTC, datetime, timedelta
from pathlib import Path

from schoolbookd.policy.output_check import OutputCheck, looks_like_distress
from schoolbookd.policy.tools import PolicyContext, ToolPolicy
from schoolbookd.policy.unlock import UnlockState, attempt_unlock, hash_password


def _ctx() -> PolicyContext:
    return PolicyContext(
        skills={"math.counting.to20"},
        image_ids={"volcano"},
        approved_videos={"abcdefghijk"},
        blocked_videos={"blockedvideo"},
        enabled_apps={"gcompris"},
        app_activities={"gcompris": {"enumerate"}},
        playing_video="abcdefghijk",
    )


def test_unknown_tool_is_denied() -> None:
    decision = ToolPolicy().check("browse", {"url": "https://example.com"}, _ctx())
    assert not decision.allowed


def test_tool_limit_blocks_the_seventh_call() -> None:
    ctx = _ctx()
    ctx.tool_calls_used = 6
    decision = ToolPolicy().check("suggest_break", {}, ctx)
    assert not decision.allowed


def test_show_board_rejects_urls_and_unknown_images() -> None:
    policy = ToolPolicy()
    url = policy.check(
        "show_board",
        {"elements": [{"type": "big_text", "text": "https://x"}]},
        _ctx(),
    )
    missing = policy.check(
        "show_board",
        {"elements": [{"type": "image", "image_id": "nope"}]},
        _ctx(),
    )
    ok = policy.check(
        "show_board",
        {"elements": [{"type": "image", "image_id": "volcano"}]},
        _ctx(),
    )
    assert not url.allowed
    assert not missing.allowed
    assert ok.allowed


def test_show_picture_needs_a_short_topic() -> None:
    policy = ToolPolicy()
    assert not policy.check("show_picture", {"topic": ""}, _ctx()).allowed
    assert not policy.check("show_picture", {"topic": "x" * 81}, _ctx()).allowed
    assert policy.check("show_picture", {"topic": "dinosaur"}, _ctx()).allowed


def test_ask_choice_bounds() -> None:
    policy = ToolPolicy()
    too_many = [{"id": str(i), "label": "Yes"} for i in range(5)]
    assert not policy.check("ask_choice", {"prompt": "Pick", "options": too_many}, _ctx()).allowed
    short = [{"id": "a", "label": "Sharks"}, {"id": "b", "label": "Trains"}]
    assert policy.check("ask_choice", {"prompt": "Which one?", "options": short}, _ctx()).allowed


def test_play_video_requires_an_approved_unblocked_id() -> None:
    policy = ToolPolicy()
    assert not policy.check("play_video", {"video_id": "notvetted1"}, _ctx()).allowed
    assert not policy.check("play_video", {"video_id": "blockedvideo"}, _ctx()).allowed
    assert policy.check("play_video", {"video_id": "abcdefghijk"}, _ctx()).allowed


def test_launch_app_uses_only_manifest_activities() -> None:
    policy = ToolPolicy()
    denied = policy.check("launch_app", {"app_id": "bash", "activity": "enumerate"}, _ctx())
    assert not denied.allowed
    bad = policy.check("launch_app", {"app_id": "gcompris", "activity": "quit"}, _ctx())
    good = policy.check("launch_app", {"app_id": "gcompris", "activity": "enumerate"}, _ctx())
    assert not bad.allowed
    assert good.allowed


def test_record_observation_requires_a_known_skill() -> None:
    policy = ToolPolicy()
    denied = policy.check(
        "record_observation",
        {"skill_id": "nope", "outcome": "correct", "evidence": "counted"},
        _ctx(),
    )
    allowed = policy.check(
        "record_observation",
        {"skill_id": "math.counting.to20", "outcome": "with_help", "evidence": "needed a hint"},
        _ctx(),
    )
    assert not denied.allowed
    assert allowed.allowed


def test_flag_is_allowed_for_high_severity() -> None:
    decision = ToolPolicy().check(
        "flag_for_parent",
        {"severity": "high", "reason": "child said someone is hurting him"},
        _ctx(),
    )
    assert decision.allowed


def test_video_control_needs_a_playing_video() -> None:
    ctx = _ctx()
    ctx.playing_video = None
    assert not ToolPolicy().check("video_control", {"action": "pause"}, ctx).allowed
    assert ToolPolicy().check("video_control", {"action": "seek", "at_s": 12}, _ctx()).allowed


def test_unlock_locks_after_five_failures() -> None:
    password_hash = hash_password("correct horse")
    state = UnlockState()
    now = datetime(2026, 10, 7, tzinfo=UTC)
    for _ in range(4):
        ok, state = attempt_unlock("nope", password_hash, state, now)
        assert not ok
        assert state.locked_until is None
    ok, state = attempt_unlock("nope", password_hash, state, now)
    assert not ok
    assert state.locked_until == now + timedelta(seconds=300)
    still, state = attempt_unlock("correct horse", password_hash, state, now + timedelta(seconds=10))
    assert not still
    opened, state = attempt_unlock("correct horse", password_hash, state, now + timedelta(seconds=301))
    assert opened
    assert state.failures == 0


def test_output_check_replaces_a_blocked_word(tmp_path: Path) -> None:
    path = tmp_path / "output-check.txt"
    path.write_text("# comment\npassword\nre:home address\n", encoding="utf-8")
    checker = OutputCheck.load(path)
    hit = checker.inspect("Tell me your password.")
    assert hit is not None
    assert "wondering" in hit.replacement
    assert checker.inspect("Count the sharks.") is None
    assert looks_like_distress("someone is hurting me")
    assert not looks_like_distress("I like sharks")
